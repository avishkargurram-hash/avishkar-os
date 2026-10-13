"""Run: python -m layla_almanac  (env: ALMANAC_DB, ALMANAC_FAMILY_DB, ALMANAC_TOKEN, ALMANAC_TOOL_TOKEN,
ALMANAC_PORT, ALMANAC_HOST)."""

import os
import sys

from .hub import Hub
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
    srv = serve(st, token, tool_token, e.get("ALMANAC_HOST", "127.0.0.1"), int(e.get("ALMANAC_PORT", "8150")), hub)
    print(f"layla_almanac on {srv.server_address}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
