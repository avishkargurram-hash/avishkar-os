# God's Eye View (GEV) — Planetary Intelligence for Layla

Integrates God's Eye View (a real-time 3D planetary intelligence and geospatial OSINT platform) into Layla without introducing redundant voice loops or unmetered third-party costs.

---

## 1. Architecture Topology

```
+-------------------------------------------------------+
|  tv-mum-01 (103.168.22.202)                          |
|  Service: gods-eye-view.service (systemd)             |
|  Runtime: Node.js 20.20.2 / Vite Dev & MCP Server      |
|  Port: 0.0.0.0:4173                                   |
|  Auth: X-GEV-Key token authentication                  |
+-------------------------------------------------------+
                           ^
                           | JSON-RPC 2.0 over HTTP (/mcp)
                           v
+-------------------------------------------------------+
|  Oracle Server (129.225.72.80) / layla.tryvanta.in    |
|  Service: layla-brain.service (systemd, port 8100)    |
|  Plugin: layla_godseye.py (MCP Client)                |
|  Catalog: gev_catalog.json (29 spatial tools)         |
|  SSE Bus: push_event -> /events                       |
|  Web UI: /opt/layla/web/face/index.html               |
+-------------------------------------------------------+
                           |
                           | SSE push ("open_panel", panel="globe")
                           v
+-------------------------------------------------------+
|  Client Browser (Face UI / Screens)                  |
|  Modal: #layla-globe-panel                            |
|  Embed: <iframe src="http://103.168.22.202:4173/?embed=1#..."> |
|  Actions: [Full Screen ↗], [Minimize —], [Close ✕]    |
+-------------------------------------------------------+
```

---

## 2. Tool Catalog (29 Live Tools)

All tools are registered with Layla's conversational tool dispatcher with schema validation:
- **Orbital & Space:** `satellites_overhead`, `satellite_pass_details`, `search_satellites`, `get_recent_launches`, `get_upcoming_launches`, `iss_location`
- **Aviation & Maritime:** `aircraft_in_area`, `military_aircraft_in_area`, `aircraft_details`, `flight_radar_area`, `vessels_in_area`, `vessel_details`
- **Geophysical & Hazards:** `get_earthquakes`, `get_earthquake_details`, `get_wildfires`, `active_cyclones`, `weather_radar_tile`, `get_elevation`
- **Infrastructure & Ground:** `get_cctv_cameras`, `cctv_snapshot`, `get_alpr_locations`, `get_street_imagery`, `submarine_cables_in_area`, `datacenters_in_area`, `dams_in_area`
- **Camera & Views:** `fly_to_location`, `set_camera_view`, `look_at_target`, `surface_view_link`

---

## 3. Configuration & Kill Switch

Defined in `/opt/layla/.env` on Oracle:
```bash
# God's Eye View planetary intelligence
GODSEYE=1
GODSEYE_URL=http://103.168.22.202:4173/mcp
GODSEYE_KEY=d53a5c29fd677344dcc67a8e8cf1854dd7a9a9af5ed64e52abb2a641eb61da48
GODSEYE_PUBLIC_URL=http://103.168.22.202:4173
```

- **Kill switch:** Setting `GODSEYE=0` disables all tool execution instantly and cleanly returns:
  `{"status": "error", "error": "God's Eye View capability is disabled (GODSEYE=0)"}`.
- Zero exceptions bubble into caller.

---

## 4. Security & CSP Framing

- **MCP Endpoint Security:** `server/mcp/plugin.js` on `tv-mum-01` verifies `X-GEV-Key` matching `GEV_API_SECRET`. Any unauthorized remote access returns HTTP 403 Forbidden.
- **Iframe Embedding:** Configured with `GEV_EMBED_FRAME_ANCESTORS=*` in `/opt/gods-eye-view/.env` on `tv-mum-01`. Whenever `?embed=1` is requested, `X-Frame-Options` and `frame-ancestors 'none'` restrictions are lifted for embed mode.
- **Direct Navigation:** The UI modal includes a `Full Screen ↗` button opening the 3D globe in a new tab, completely immune to browser mixed-content restrictions.
