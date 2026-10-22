import datetime as dt
import json
import threading
import urllib.error
import urllib.request

import pytest

from layla_almanac.server import serve
from layla_almanac.store import AlmanacStore, ValidationError
from layla_almanac.summary import build_summary

TOKEN = "a" * 32
TOOL = "b" * 32
NOW = dt.datetime(2026, 10, 7, 9, 0, tzinfo=dt.timezone.utc)  # a Wednesday
TODAY = "2026-10-07"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock(NOW.timestamp())


@pytest.fixture
def store(clock):
    return AlmanacStore(":memory:", clock=clock)


@pytest.fixture
def api(store):
    srv = serve(store, TOKEN, TOOL, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/api/almanac"
    yield base
    srv.shutdown()
    srv.server_close()


def call(url, method="GET", body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), r.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw else None), e.headers


def ms(clock, delta_s=0):
    return int((clock.t + delta_s) * 1000)


# ---- store ----

def test_lww_newer_wins_older_ignored(store, clock):
    u = ms(clock)
    store.merge({"ev:1": {"u": u + 2000, "v": {"title": "new"}}}, {})
    store.merge({"ev:1": {"u": u + 1000, "v": {"title": "old"}}}, {})
    assert store.get("ev:1")["title"] == "new"


def test_tombstone_beats_older_write_and_is_beaten_by_newer(store, clock):
    u = ms(clock)
    store.merge({"ev:1": {"u": u + 1000, "v": {"title": "x"}}}, {})
    store.merge({}, {"ev:1": u + 2000})
    assert store.get("ev:1") is None
    store.merge({"ev:1": {"u": u + 1500, "v": {"title": "stale"}}}, {})
    assert store.get("ev:1") is None
    store.merge({"ev:1": {"u": u + 3000, "v": {"title": "back"}}}, {})
    assert store.get("ev:1")["title"] == "back"


def test_changes_since_is_incremental(store, clock):
    u = ms(clock)
    store.merge({"ev:1": {"u": u, "v": {}}}, {})
    _, _, rev1 = store.changes_since(0)
    store.merge({"ev:2": {"u": u, "v": {}}}, {"ev:1": u + 5})
    recs, tombs, rev2 = store.changes_since(rev1)
    assert set(recs) == {"ev:2"} and set(tombs) == {"ev:1"} and rev2 > rev1


def test_old_tombstones_are_purged_after_retention(store, clock):
    store.merge({}, {"ev:1": 5})
    assert store.changes_since(0)[1] == {}


def test_noop_merge_does_not_bump_rev(store):
    store.merge({"ev:1": {"u": 5, "v": {}}}, {})
    _, _, r1 = store.changes_since(0)
    store.merge({"ev:1": {"u": 5, "v": {}}}, {})
    assert store.changes_since(0)[2] == r1


@pytest.mark.parametrize("recs", [
    {"bad key": {"u": 1, "v": {}}},
    {"ev:1": {"u": 1}},
    {"ev:1": {"u": "x", "v": {}}},
    {"ev:1": {"u": -1, "v": {}}},
    {"ev:1": {"u": 1, "v": []}},
    {"ro:2026-01-01": {"u": 1, "v": {}}},
    {"goal": {"u": 1, "v": "2500"}},
    {"goal": {"u": 1, "v": 0}},
    {"goal": {"u": 1, "v": True}},
    {"ev:../x": {"u": 1, "v": {}}},
])
def test_validation_rejects_bad_records(store, recs):
    with pytest.raises(ValidationError):
        store.merge(recs, {})


def test_validation_is_all_or_nothing(store):
    with pytest.raises(ValidationError):
        store.merge({"ev:1": {"u": 1, "v": {}}, "nope": {"u": 1, "v": {}}}, {})
    assert store.get("ev:1") is None


def test_future_timestamp_is_clamped(store, clock):
    store.merge({"ev:1": {"u": ms(clock, 10 ** 8), "v": {"t": 1}}}, {})
    recs, _, _ = store.changes_since(0)
    assert recs["ev:1"]["u"] <= ms(clock, 301)


def test_oversize_record_rejected(store):
    with pytest.raises(ValidationError):
        store.merge({"note:1": {"u": 1, "v": {"body": "x" * (600 * 1024)}}}, {})


def test_templates_sanitised(store):
    store.merge({}, {}, {"default": [{"id": "t0", "time": "6", "title": "Wake", "evil": 1}], "monday": []})
    assert store.templates()["default"][0] == {"id": "t0", "time": "6", "title": "Wake", "desc": ""}
    store.merge({}, {}, {"default": "nope"})
    assert store.templates() is not None  # bad templates ignored, old kept


# ---- HTTP ----

def test_ping_open_everything_else_requires_secret(api):
    assert call(api + "/ping")[0] == 200
    assert call(api + "/state")[0] == 401
    assert call(api + "/state", headers={"X-Layla-Secret": "wrong"})[0] == 401
    assert call(api + "/sync", "POST", {}, {})[0] == 401
    assert call(api + "/state", headers={"X-Layla-Secret": TOKEN})[0] == 200


def test_cors_preflight(api):
    code, _, h = call(api + "/sync", "OPTIONS")
    assert code == 204
    assert "x-layla-secret" in h["Access-Control-Allow-Headers"].lower()
    assert h["Access-Control-Allow-Origin"] == "*"


def test_sync_roundtrip_and_incremental_pull(api, clock):
    H = {"X-Layla-Secret": TOKEN, "Content-Type": "application/json"}
    code, d, _ = call(api + "/sync", "POST", {"since": 0, "records": {
        "ev:a": {"u": ms(clock), "v": {"title": "Dentist", "date": TODAY}}}}, H)
    assert code == 200 and d["applied"] == 1 and "ev:a" in d["records"]
    rev = d["rev"]
    code, d, _ = call(api + f"/state?since={rev}", headers=H)
    assert d["records"] == {} and d["rev"] == rev
    code, d, _ = call(api + "/state", headers=H)
    assert "ev:a" in d["records"]


def test_sync_rejects_garbage(api):
    H = {"X-Layla-Secret": TOKEN}
    assert call(api + "/sync", "POST", {"records": []}, H)[0] == 400
    assert call(api + "/sync", "POST", {"records": {"x": {"u": 1, "v": {}}}}, H)[0] == 400
    assert call(api + "/sync", "POST", {"tombstones": []}, H)[0] == 400
    assert call(api + "/state?since=abc", headers=H)[0] == 400


def test_sync_body_too_large(api):
    H = {"X-Layla-Secret": TOKEN}
    big = {"records": {}, "pad": "x" * (2 * 1024 * 1024 + 10)}
    assert call(api + "/sync", "POST", big, H)[0] == 400


def test_tokens_are_not_interchangeable(api):
    assert call(api + "/tool/get_almanac_state", "POST", {}, {"X-Layla-Secret": TOKEN})[0] == 401
    assert call(api + "/state", headers={"X-Layla-Secret": TOOL})[0] == 401
    assert call(api + "/sync", "POST", {}, {"X-Layla-Secret": TOOL})[0] == 401
    assert call(api + "/tool/get_almanac_state", "POST", {}, {"X-Layla-Secret": TOOL})[0] == 200
    assert call(api + "/tool/get_almanac_state", "POST", {}, {"Authorization": "Bearer " + TOOL})[0] == 200


def test_unknown_path_404(api):
    assert call(api + "/nope", headers={"X-Layla-Secret": TOKEN})[0] == 404


# ---- summary ----

def seed(store, clock):
    u = ms(clock)
    store.merge({
        "goal": {"u": u, "v": 3000},
        f"wd:{TODAY}": {"u": u, "v": {"ml": 1200}},
        f"rd:{TODAY}": {"u": u, "v": {"t0": True, "t1": True}},
        "ev:1": {"u": u, "v": {"title": "Dentist", "date": "2026-10-09", "time": "10:00", "notes": "SECRET"}},
        "ev:2": {"u": u, "v": {"title": "Past", "date": "2026-10-01"}},
        "ev:3": {"u": u, "v": {"title": "Far", "date": "2027-01-01"}},
        "rem:1": {"u": u, "v": {"title": "Call mom", "time": "18:00", "done": False}},
        "rem:2": {"u": u, "v": {"title": "Done one", "done": True}},
        "note:1": {"u": u, "v": {"title": "Ideas", "body": "PRIVATE BODY", "updatedAt": u - 1000}},
        "note:2": {"u": u, "v": {"title": "Newer", "body": "x", "updatedAt": u}},
        "well:1": {"u": u, "v": {"name": "Yoga", "cat": "move", "dur": 1800, "ts": u - 3600 * 1000}},
    }, {}, {"default": [{"id": "t0", "time": "6:00", "title": "Wake"}, {"id": "t1", "time": "7:00", "title": "Run"},
                        {"id": "t2", "time": "8:00", "title": "Breakfast"}],
            "monday": [{"id": "m0", "time": "6:00", "title": "Monday only"}]})


def test_summary_never_synced(store):
    s = build_summary(store)
    assert s["ok"] is False and "never synced" in s["message"]


def test_summary_content(store, clock):
    seed(store, clock)
    s = build_summary(store)
    assert s["date"] == TODAY
    assert s["water"] == {"current_ml": 1200, "goal_ml": 3000, "percent": 40, "remaining_ml": 1800}
    assert s["routine"]["completed_count"] == 2 and s["routine"]["total"] == 3
    assert s["routine"]["pending"] == [{"time": "8:00", "title": "Breakfast"}]
    assert [e["title"] for e in s["upcoming_events"]] == ["Dentist"]
    assert [r["title"] for r in s["open_reminders"]] == ["Call mom"]
    assert [n["title"] for n in s["recent_notes"]] == ["Newer", "Ideas"]
    assert s["wellness_7d"]["sessions"] == 1 and s["wellness_7d"]["minutes"] == 30


def test_summary_leaks_no_private_text(store, clock):
    seed(store, clock)
    blob = json.dumps(build_summary(store))
    assert "PRIVATE BODY" not in blob and "SECRET" not in blob


def test_summary_uses_override_and_monday_template(store, clock):
    seed(store, clock)
    store.merge({f"ro:{TODAY}": {"u": ms(clock) + 1, "v": [{"id": "x", "time": "9", "title": "Custom"}]}}, {})
    s = build_summary(store)
    assert s["routine"]["source"] == "edited_for_today" and s["routine"]["total"] == 1
    mon = build_summary(store, "2026-10-05")
    assert mon["routine"]["source"] == "default_template" and mon["routine"]["pending"][0]["title"] == "Monday only"


def test_summary_stale_warning(store, clock):
    seed(store, clock)
    clock.t += 7 * 3600
    assert "stale_warning" in build_summary(store)


def test_summary_sanitises_control_chars_and_truncates(store, clock):
    store.merge({"rem:1": {"u": ms(clock), "v": {"title": "a\x00b\x1b" + "z" * 500, "done": False}}}, {})
    t = build_summary(store)["open_reminders"][0]["title"]
    assert "\x00" not in t and "\x1b" not in t and len(t) <= 80


def test_tool_endpoint_end_to_end(api, store, clock):
    seed(store, clock)
    code, d, _ = call(api + "/tool/get_almanac_state", "POST", {}, {"X-Layla-Secret": TOOL})
    assert code == 200 and d["water"]["current_ml"] == 1200
