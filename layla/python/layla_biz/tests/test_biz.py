import json
import threading
import urllib.error
import urllib.request

from layla_biz.admin import handle_command
from layla_biz.config import Config
from layla_biz.server import serve
from layla_biz.store import BizStore
from layla_biz.tools import CALLBACK_NOTED, NOT_STATED, PAUSED, Tools
from layla_wa.store import WaStore
from layla_wa.telegram import Controller

SECRET = "s" * 32
ADMIN = "a" * 32


class FakeNotify:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


def make(on=True, **cfg):
    kn = open("layla_biz/knowledge.md", encoding="utf-8").read()
    st = BizStore(":memory:")
    if on:
        st.set_enabled(True)
    n = FakeNotify()
    return st, n, Tools(st, n, Config(knowledge=kn, **cfg))


def test_default_off_blocks_every_tool():
    st, n, t = make(on=False)
    for fn in (t.get_offering, t.capture_lead, t.request_callback, t.escalate):
        r = fn({"caller_id": "919800000001", "topic": "piano", "name": "A"})
        assert r["ok"] is False and r["message"] == PAUSED
    assert n.sent == [] and st.recent_leads() == []


def test_get_offering_returns_only_approved_text():
    _, _, t = make()
    r = t.get_offering({"caller_id": "1", "topic": "piano lessons"})
    assert r["found"] and r["offerings"][0]["title"].startswith("Music classes")
    assert "Trinity" in json.dumps(r) and "Not stated here" in r["never_state"]
    h = t.get_offering({"caller_id": "1", "topic": "smart switchboard"})
    assert h["offerings"][0]["title"] == "Tryvanta Home Automation"


def test_unknown_topic_gives_not_stated_not_a_guess():
    _, _, t = make()
    r = t.get_offering({"caller_id": "1", "topic": "price of a 3 bedroom flat"})
    assert r["found"] is False and r["message"] == NOT_STATED


def test_capture_lead_stores_alerts_and_dedupes():
    st, n, t = make()
    d = {"caller_id": "+91 98000 00001", "name": "Ravi", "interest": "piano", "details": "daughter, age 9"}
    assert t.capture_lead(d)["message"] == CALLBACK_NOTED
    assert len(n.sent) == 1 and n.sent[0].startswith("[Lead]") and "Ravi" in n.sent[0]
    t.capture_lead(d)
    assert len(n.sent) == 1
    t.capture_lead({"caller_id": "919800000001", "preferred_time": "evenings"})
    assert len(n.sent) == 2
    lead = st.get_lead("919800000001")
    assert lead["name"] == "Ravi" and lead["preferred_time"] == "evenings" and lead["phone"] == "919800000001"


def test_callback_never_promises_a_time():
    _, n, t = make()
    r = t.request_callback({"caller_id": "9198", "name": "Sam", "preferred_time": "tomorrow 5pm"})
    assert "personally" in r["message"] and "5pm" not in r["message"]
    assert n.sent[0].startswith("[Callback requested]") and "tomorrow 5pm" in n.sent[0]


def test_escalate_alerts_owner():
    _, n, t = make()
    t.escalate({"caller_id": "9198", "reason": "angry about a refund"})
    assert n.sent[0].startswith("[Needs you]") and "refund" in n.sent[0]


def test_init_returns_all_variables_even_for_unknown_caller_and_empty_body():
    _, _, t = make()
    for body in ({}, {"caller_id": "123", "called_number": "x"}):
        v = t.init_vars(body)["dynamic_variables"]
        assert set(v) == {"caller_id", "owner_name", "business_name", "is_returning_lead", "lead_name",
                          "automation_status"}
        assert all(isinstance(x, str) and x for x in v.values())
    t.capture_lead({"caller_id": "123", "name": "Meera"})
    v = t.init_vars({"caller_id": "123"})["dynamic_variables"]
    assert v["is_returning_lead"] == "yes" and v["lead_name"] == "Meera"


def test_input_is_sanitised_and_capped():
    st, _, t = make()
    t.capture_lead({"caller_id": "5", "name": "x\x00\x07" + "y" * 500, "details": {"a": 1}})
    assert "\x00" not in st.get_lead("5")["name"] and len(st.get_lead("5")["name"]) <= 80


def test_rate_limit_per_caller():
    _, _, t = make(per_caller_per_hour=3)
    for _ in range(3):
        assert t.get_offering({"caller_id": "7", "topic": "piano"})["ok"]
    r = t.get_offering({"caller_id": "7", "topic": "piano"})
    assert r["ok"] is False
    assert t.get_offering({"caller_id": "8", "topic": "piano"})["ok"]


def test_admin_commands_toggle_switch():
    st, _, _ = make(on=False)
    assert handle_command(st, "/wa on") is None
    handle_command(st, "/biz on")
    assert st.enabled()
    assert "OFF" in handle_command(st, "/biz off") and not st.enabled()
    assert "Leads captured: 0" in handle_command(st, "/biz status")


def _call(port, path, body=None, token=SECRET, method="POST", headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}",
                                 data=None if method == "GET" else json.dumps(body or {}).encode(),
                                 headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_http_auth_routes_and_admin():
    st, n, t = make()
    srv = serve(t, SECRET, port=0, admin_token=ADMIN, admin=lambda text: handle_command(st, text))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _call(port, "/biz/tool/get_offering", {"topic": "piano"}, token="")[0] == 401
        assert _call(port, "/biz/tool/get_offering", {"topic": "piano"}, token="wrong")[0] == 401
        code, r = _call(port, "/biz/tool/get_offering", {"caller_id": "1", "topic": "piano"})
        assert code == 200 and r["found"]
        code, r = _call(port, "/biz/tool/get_offering", {"caller_id": "1", "topic": "piano"},
                        token="", headers={"X-Layla-Secret": SECRET})
        assert code == 200
        assert _call(port, "/biz/init", {"caller_id": "1"})[1]["type"] == "conversation_initiation_client_data"
        assert _call(port, "/biz/tool/nope", {})[0] == 404
        assert _call(port, "/biz/ping", method="GET")[1]["enabled"] is True
        assert _call(port, "/biz/admin/cmd", {"text": "/biz off"}, token=ADMIN)[0] == 401
        assert st.enabled()
        assert _call(port, "/admin/cmd", {"text": "/biz off"}, token=SECRET)[0] == 401
        code, r = _call(port, "/admin/cmd", {"text": "/biz off"}, token=ADMIN)
        assert code == 200 and "OFF" in r["reply"] and not st.enabled()
        assert _call(port, "/biz/tool/capture_lead", {"caller_id": "1", "name": "x"})[1]["message"] == PAUSED
    finally:
        srv.shutdown()


def test_telegram_controller_forwards_biz_and_ignores_other_chats():
    wa = WaStore(":memory:")
    seen = []

    def fwd(url, tok, text):
        seen.append((url, tok, text))
        return "forwarded"

    sent = []

    def http(url):
        if "getUpdates" in url:
            return {"result": [
                {"update_id": 1, "message": {"chat": {"id": 42}, "text": "/biz status"}},
                {"update_id": 2, "message": {"chat": {"id": 99}, "text": "/biz on"}},
                {"update_id": 3, "message": {"chat": {"id": 42}, "text": "/wa status"}},
                {"update_id": 4, "message": {"chat": {"id": 42}, "text": "hello"}}]}
        sent.append(url)
        return {}

    c = Controller(wa, "tok", "42", http=http, forwards={"/biz": ("http://x/admin/cmd", "T")}, forwarder=fwd)
    assert c.poll_once() == 2
    assert seen == [("http://x/admin/cmd", "T", "/biz status")]
