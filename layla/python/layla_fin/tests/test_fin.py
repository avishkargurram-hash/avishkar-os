import datetime as dt
import json
import threading
import urllib.error
import urllib.request

from layla_fin.admin import handle_command
from layla_fin.monitor import Monitor
from layla_fin.parse import parse_alert
from layla_fin.server import serve
from layla_fin.store import IST, FinStore, add_cycle

ADMIN = "a" * 32


class Clock:
    def __init__(self, day="2026-10-06", hour=10):
        self.t = dt.datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=IST).timestamp()

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class Notify:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


def make(**kw):
    clk = Clock(**kw)
    st = FinStore(":memory:", clk)
    n = Notify()
    return st, n, clk


def test_add_cycle_clamps_month_end():
    assert add_cycle(dt.date(2026, 1, 31), "monthly") == dt.date(2026, 2, 28)
    assert add_cycle(dt.date(2026, 12, 15), "monthly") == dt.date(2027, 1, 15)
    assert add_cycle(dt.date(2024, 2, 29), "yearly") == dt.date(2025, 2, 28)
    assert add_cycle(dt.date(2026, 1, 1), "weekly") == dt.date(2026, 1, 8)


def test_expense_adjusts_balance_and_totals():
    st, _, _ = make()
    st.set_account("hdfc", kind="bank", balance=10000)
    st.add_expense(250, "food", "zomato", "hdfc")
    assert st.accounts()[0]["balance"] == 9750
    s, e = st.day_bounds(st.today())
    assert st.spent_between(s, e) == {"INR": 250}
    ms, me = st.month_bounds(st.today())
    assert st.spent_by_category(ms, me)[0]["category"] == "food"


def test_subscription_mark_paid_rolls_and_records_expense():
    st, _, _ = make()
    st.set_sub("hostinger", 800, "monthly", "2026-10-31")
    assert st.mark_paid("hostinger") == "2026-11-30"
    assert st.subs()[0]["next_due"] == "2026-11-30"
    ms, me = st.month_bounds(st.today())
    assert st.spent_between(ms, me) == {"INR": 800}
    assert st.mark_paid("nope") is None


def test_set_sub_rejects_bad_input():
    st, _, _ = make()
    for args in (("x", 1, "daily", "2026-10-31"), ("x", 1, "monthly", "not-a-date")):
        try:
            st.set_sub(*args)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def test_low_balance_alert_fires_once_per_day():
    st, n, clk = make(hour=7)
    st.set_account("hdfc", balance=900, low=1000)
    mon = Monitor(st, n, digest_hour=23)
    assert any("[Low balance]" in a for a in mon.checks())
    assert mon.checks() == []
    clk.advance(25 * 3600)
    assert any("[Low balance]" in a for a in mon.checks())
    assert all("[Low balance]" in s for s in n.sent)


def test_balance_above_threshold_is_silent():
    st, n, _ = make(hour=7)
    st.set_account("hdfc", balance=5000, low=1000)
    assert Monitor(st, n, digest_hour=23).checks() == []


def test_credit_polling_sets_remaining_and_default_threshold():
    st, n, _ = make()
    mon = Monitor(st, n, "key", fetch=lambda k: {"character_limit": 26000, "character_count": 1000})
    assert mon.poll_providers() is None
    c = st.credits()[0]
    assert c["name"] == "elevenlabs" and c["remaining"] == 25000 and c["low"] == 2600 and c["source"] == "api"


def test_low_credit_alert_and_poll_failure_never_raises():
    st, n, _ = make(hour=7)
    mon = Monitor(st, n, "key", digest_hour=23,
                  fetch=lambda k: {"character_limit": 26000, "character_count": 25000})
    mon.tick()
    assert any(s.startswith("[Low credits] elevenlabs") for s in n.sent)

    def boom(k):
        raise RuntimeError("network down")

    bad = Monitor(st, n, "key", fetch=boom)
    assert "failed" in bad.poll_providers()


def test_credit_runway_warning_from_burn_rate():
    st, n, clk = make(hour=7)
    st.set_credit("elevenlabs", remaining=10000, total=26000, low=500)
    clk.advance(86400)
    st.set_credit("elevenlabs", remaining=4000)
    out = Monitor(st, n, digest_hour=23).checks()
    assert any("[Credit runway]" in a for a in out)


def test_subscription_renewal_alerts():
    st, n, clk = make(hour=7)
    st.set_sub("vps", 500, "monthly", "2026-10-08")
    st.set_sub("later", 100, "monthly", "2026-11-30")
    mon = Monitor(st, n, digest_hour=23)
    out = mon.checks()
    assert len(out) == 1 and "vps" in out[0] and "due in 2 day" in out[0]
    assert mon.checks() == []
    clk.advance(2 * 86400)
    assert "due today" in mon.checks()[0]
    clk.advance(86400)
    assert "overdue by 1" in mon.checks()[0]


def test_daily_digest_sent_once_after_digest_hour():
    st, n, clk = make(hour=8)
    st.set_account("hdfc", balance=5000, low=100)
    st.add_expense(300, "food", account="hdfc")
    mon = Monitor(st, n, digest_hour=9)
    assert mon.checks() == []
    clk.advance(3600)
    out = mon.checks()
    assert len(out) == 1 and out[0].startswith("Finance digest") and "hdfc" in out[0]
    assert mon.checks() == []


def test_notifier_failure_does_not_break_checks():
    st, _, _ = make(hour=7)
    st.set_account("hdfc", balance=1, low=100)

    class Bad:
        def send(self, t):
            raise RuntimeError("telegram down")

    assert Monitor(st, Bad(), digest_hour=23).checks()


def test_parse_debit_credit_and_balance():
    d = parse_alert("Rs.1,250.50 debited from A/c XX1234 on 06-10-26 to VPA zomato@icici (UPI Ref 123). "
                    "Avl bal Rs 8,749.50")
    assert d["direction"] == "debit" and d["amount"] == 1250.5 and d["balance"] == 8749.5 and d["channel"] == "upi"
    c = parse_alert("INR 5000 credited to your account. Available balance: INR 13,000")
    assert c["direction"] == "credit" and c["amount"] == 5000 and c["balance"] == 13000


def test_parse_refuses_ambiguous_or_irrelevant_text():
    assert parse_alert("Your OTP is 123456") is None
    assert parse_alert("Rs 500 debited and Rs 500 credited") is None
    assert parse_alert("Avl bal Rs 100") is None


def test_admin_flow_end_to_end():
    st, _, _ = make()
    assert handle_command(st, "/biz on") is None and handle_command(st, "hello") is None
    handle_command(st, "/fin account hdfc bank low 1000")
    handle_command(st, "/fin bal hdfc 10000")
    assert "Logged" in handle_command(st, "/fin spent 400 food zomato lunch @hdfc")
    assert st.accounts()[0]["balance"] == 9600
    handle_command(st, "/fin credit set elevenlabs 26000 total 26000 unit credits")
    handle_command(st, "/fin credit low elevenlabs 3000")
    c = st.credits()[0]
    assert c["remaining"] == 26000 and c["low"] == 3000
    assert "saved" in handle_command(st, "/fin sub add hostinger 800 monthly 2026-10-20")
    assert "hostinger" in handle_command(st, "/fin sub list")
    assert "Next due 2026-11-20" in handle_command(st, "/fin sub paid hostinger")
    assert "Removed" in handle_command(st, "/fin sub del hostinger")
    assert "400" in handle_command(st, "/fin month")
    assert "hdfc" in handle_command(st, "/fin status")


def test_admin_bad_input_returns_help_not_crash():
    st, _, _ = make()
    for cmd in ("/fin spent abc food", "/fin spent", "/fin sub add x 1 daily 2026-01-01", "/fin bal", "/fin wat",
                "/fin spent -5 food", "/fin credit set x"):
        assert "/fin" in handle_command(st, cmd)
    assert st.accounts() == [] and st.subs() == []


def test_sms_updates_matched_account_balance():
    st, _, _ = make()
    handle_command(st, "/fin account hdfc bank")
    r = handle_command(st, "/fin sms Rs 300 debited from hdfc A/c to VPA tea@upi. Avl bal Rs 7,000")
    assert "Logged spend" in r and "hdfc" in r
    assert st.accounts()[0]["balance"] == 7000
    assert "Could not read" in handle_command(st, "/fin sms Your OTP is 1234")


def test_http_admin_auth_and_loopback():
    st, _, _ = make()
    srv = serve(lambda t: handle_command(st, t), ADMIN, port=0)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    def call(token, body):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"http://127.0.0.1:{port}/admin/cmd", data=json.dumps(body).encode(),
                                     headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        assert call("", {"text": "/fin month"})[0] == 401
        assert call("wrong", {"text": "/fin month"})[0] == 401
        code, r = call(ADMIN, {"text": "/fin spent 10 tea"})
        assert code == 200 and "Logged" in r["reply"]
    finally:
        srv.shutdown()
