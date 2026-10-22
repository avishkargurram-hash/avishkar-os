"""Run: python -m layla_almanac  (env: ALMANAC_DB, ALMANAC_FAMILY_DB, ALMANAC_TOKEN, ALMANAC_TOOL_TOKEN,
ALMANAC_PORT, ALMANAC_HOST, ALMANAC_BODY=0 to disable robot/AV box, ALMANAC_MQTT_HOST, ALMANAC_MQTT_PORT)."""

import os
import sys

from .body import Body, subscriptions
from .hub import Hub
from .mqtt import MqttClient
from .presence import Presence
from .server import serve
from .store import AlmanacStore


def main() -> int:
    e = os.environ
    token, tool_token = e.get("ALMANAC_TOKEN", ""), e.get("ALMANAC_TOOL_TOKEN", "")
    if len(token) < 24 or len(tool_token) < 24 or token == tool_token:
        print("ALMANAC_TOKEN and ALMANAC_TOOL_TOKEN must be two different long random strings", file=sys.stderr)
        return 2
    db = e.get("ALMANAC_DB", "almanac.db")
    fam_db = e.get("ALMANAC_FAMILY_DB") or os.path.join(os.path.dirname(os.path.abspath(db)), "almanac_family.db")
    st = AlmanacStore(db)
    hub = Hub(fam_db)
    body = None
    if e.get("ALMANAC_BODY", "1") != "0":
        mq = MqttClient(e.get("ALMANAC_MQTT_HOST", "127.0.0.1"), int(e.get("ALMANAC_MQTT_PORT", "51883")),
                        "layla-almanac-body")
        body = Body(mq.publish, hub._meta, hub._set_meta,
                    on_change=lambda s: hub.broadcast({"t": "body", **s}, owner_only=True))
        mq.on_message, mq.on_link = body.handle, body.set_link
        if e.get("ALMANAC_PRESENCE", "1") != "0":
            body.presence = Presence(body, mq.publish, hub._meta, hub._set_meta)
        for flt in subscriptions():
            mq.subscribe(flt)
        mq.start()
    srv = serve(st, token, tool_token, e.get("ALMANAC_HOST", "127.0.0.1"), int(e.get("ALMANAC_PORT", "8150")), hub,
                body)
    print(f"layla_almanac on {srv.server_address} (body {'on' if body else 'off'})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
