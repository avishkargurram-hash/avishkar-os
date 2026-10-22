# 02 — System map

## Servers

| Name | Address | Login | What runs |
|---|---|---|---|
| **Oracle VM** ("tyvanta-server") | `129.225.72.80` | user `ubuntu`, key `ssh-keys/ssh-key-2026-09-15.key`; files under `/opt/layla*` need `sudo -n` | Layla brain, Almanac, portal, WhatsApp/biz/fin services, MQTT broker, Postgres (docker), nginx |
| **tv-mum-01** | `103.168.22.202`, **SSH port 3052** | user `root`, key `ssh-keys/tv-mum-01.key` | 9-agent runner, Scientist OS, God's-eye view, local models |
| **Owner's Windows PC** | LAN | — | Android Studio, Arduino/ESPHome tools, home laptop bridges (TV adb) |

Only ~950 MB RAM on the VM: avoid heavy commands there. SSH keys are gitignored (`ssh-keys/`).

## Services on the Oracle VM

| systemd unit | Port | Code (local repo → deployed path) | Purpose |
|---|---|---|---|
| `layla-brain` | 8100 (loopback, nginx → `layla.tryvanta.in`) | `layla/*.py`, `layla/brain-plugins/*.py` → `/opt/layla/` | Assistant, tools, plugins |
| `layla-almanac` | 8150 | `layla/python/layla_almanac/` → `/opt/layla-almanac/layla_almanac/` | Almanac sync, family, **robot/home/presence API**, WebSocket `/api/almanac/ws` |
| `layla-portal` | 8160 | → `/opt/layla-portal/layla_portal/` | Subscribe/billing site, coupons |
| `layla-wa` | 8120 | `layla/python/layla_wa/` → `/opt/layla-wa/layla_wa/` | WhatsApp auto-reply decision engine |
| `layla-biz` | 8130 | `layla/python/layla_biz/` | Business-number lead capture (keep OFF) |
| `layla-fin` | 8140 | `layla/python/layla_fin/` | Finance tracker (loopback) |
| `layla-comms-poll` (timer) | — | `layla/python/layla_comms/` | Gmail polling |
| docker `genesis-data-mosquitto-1` | 1883 (anonymous, **loopback only**, host `127.0.0.1:51883`), 8883 (TLS + passwords, public) | `/opt/genesis-data/` | **MQTT broker** |
| docker `genesis-data-postgres-1` | host `127.0.0.1:55432` | — | Postgres (portal DB `layla_tenancy`, schema `tenancy`) |
| nginx | 80/443 | `/etc/nginx/sites-enabled/` | TLS front door; `/api/almanac/*`, `/wa/`, `/biz/`, `/portal/` |

The mosquitto container has `mosquitto_pub/sub`; the VM host does not. Use
`sudo docker exec genesis-data-mosquitto-1 mosquitto_sub -h 127.0.0.1 -p 1883 -t '<topic>' -v`.

## Services on tv-mum-01

| Unit | Port | Purpose |
|---|---|---|
| `l365-runner` | 8090 (health) | Runs the 9 agents' duties (`/opt/layla365/app/l365/`) |
| `sci-api`, `sci-worker@1/2`, `sci-supervisor` | 8095 (firewalled to the VM only) | Scientist OS |
| gods-eye (Vite) | 4173 (firewalled to the VM only) | World view |
| local models | 8081/8082 | Small local LLMs |
| docker `sci-postgres` | 5433 | Scientist + agents DB |

## MQTT topics

- Robot `tryvanta/robot/001/`: `status`, `fw`, `ip`, `motor/set` (command), `motor/state`, `distance/state` (cm),
  `obstacle/state`, `pir/state`.
- AV box `layla/esp1/`: `status`, `sensor/<id>/state`, `binary_sensor/<id>/state`, `display/text` (OLED),
  `ir/transmit`, `ir/received`, `ir/request` + `ir/result` + `ir/catalog` (Almanac ↔ brain), `debug`.
  Sensor ids include `room_temperature`, `room_humidity`, `ldr_light_level`, `pir_motion`, `esp32_wifi_signal`,
  `esp32_uptime`, and the radar: `radar_presence`, `radar_moving_target`, `radar_still_target`,
  `radar_{moving,still,detection}_distance`, `radar_{moving,still}_energy`.
- Home bridge `layla/home/`: `request`, `result`, `state` (retained snapshot), `event` (presence automation notices).

## Where secrets live (names only, never values)

| Secret | Location |
|---|---|
| Brain env (API keys, tokens, Tuya, owner email, session secret) | VM `/opt/layla/.env` |
| Almanac owner/tool tokens | VM `/opt/layla-almanac/almanac.env` |
| Portal (Cashfree, DB DSN, KEK, session secret, prices) | VM `/opt/layla-portal/portal.env` |
| WhatsApp server token | VM `/opt/layla-wa/wa.env`; phone side `clients/LaylaWaAgent/wa.properties` (gitignored) |
| MQTT users/passwords | host file `/opt/genesis-data/mosquitto_passwd` (edit on the HOST, then `docker kill -s HUP genesis-data-mosquitto-1`) |
| Robot firmware WiFi/MQTT/OTA | `clients/LaylaGR-firmware/LaylaGR/secrets.h` (gitignored; template `secrets.h.example`) |
| AV box credentials | `C:\Users\Administrator\esphome\secrets.yaml` |
| Agents' DB/gateway/Telegram tokens | tv-mum-01 `/opt/layla365/secrets/*.env` (root only) |
| Android signing | `clients/Almanac/android` uses the standard debug keystore on the owner's PC (keep it: it is what lets an update install over the old app) |

Phone Agent MQTT password (user `tvphone`): **no longer in source** (moved 2026-10-22). It is read at build time from the gitignored
`clients/LaylaPhoneAgent/phone.properties` (`mqtt_pass=...`) into `BuildConfig.PHONE_MQTT_PASS` by both `clients/LaylaPhoneAgent/app/build.gradle`
and `clients/Almanac/android/phoneagent/build.gradle`. **If that file is missing the next APK builds with an empty password and the
Phone Agent cannot connect.** The password itself has NOT been rotated.

## Auth model in one paragraph

- Almanac API: header `X-Layla-Secret: <owner token>` (owner), a separate tool token (read-only summary), and per-family
  member tokens (family space only). Robot, AV box, home and presence routes are **owner only**.
- Brain owner endpoints: signed session cookie `layla_session` / `Authorization: Bearer`.
- Agents ↔ brain: the "gateway" (`layla/brain-plugins/layla_l365.py`) with per-agent tokens and an allow-list of verbs.
- Portal: Google sign-in (invite-gated), signed session cookie, Postgres row-level security per tenant.
