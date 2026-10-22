# 07 — Open items, risks and gotchas

## Open items (highest value first)

| # | Item | Why / how |
|---|---|---|
| 1 | **Re-pair the bedroom fan** in Smart Life when the owner is home | Offline since 2026-10-09; until then it cannot be read or switched remotely |
| 2 | **Renew the Tuya IoT Core trial ~mid-January 2027** | Otherwise fan + plug die again with Err 913 (see file 05) |
| 3 | Owner tests the robot on the floor: forward really goes forward, stops with a hand 15 cm ahead, left/right correct | Firmware v2 was verified electrically, directions only by reasoning |
| 4 | Install the new Almanac APK over the old one; grant permissions in **More → Layla → Phone & WhatsApp**; uninstall the old "Layla Phone Agent" and "Layla WhatsApp" apps | Otherwise two apps answer |
| 5 | Decide when to switch ON: WhatsApp auto-reply (strangers only) and Presence auto-off | Both OFF by default |
| 6 | Portal launch checks: one real payment, coupon in a real browser, webhook | Owner will plan this separately |
| 7 | **Rotate pasted secrets** (MQTT `tvrobot`/`esp1`/phone user, WiFi, Gemini/OpenRouter keys, phone-agent MQTT password in `phone.properties`) | Owner chose to skip for now. Robot can be re-flashed over WiFi; the AV box needs ESPHome re-flash; the phone-agent password is in source |
| 8 | Evolviot channel names are "Switch 1..5": rename in the Evolviot app (Bulb Light, Tube Light, Ceiling Light 1/2) or confirm the assumed mapping | Wrong mapping would switch the wrong light |
| 9 | Presence automation: radar must prove itself for a few days before it is enabled | It only trusts the radar if it saw the owner within 12 h |
| 10 | "Connect later" devices: AC, geyser, smart switch, water motor, washing machine | UI placeholders only |
| 11 | Account for ~3 GB free RAM on the Windows PC when building | Close daemons first |
| 12 | Version-control hygiene: see "Git" below | A large amount of work was uncommitted for weeks |

## Git

- Repo root: `Avishkar-OS/` (branch `main`). **No remote was configured** when this was written; add the GitHub remote before pushing.
- Files needed to build but kept OUT of git (create them again on a new PC): `clients/LaylaWaAgent/wa.properties` (`base=`, `token=`),
  `clients/LaylaPhoneAgent/phone.properties` (`mqtt_pass=`), `clients/LaylaGR-firmware/LaylaGR/secrets.h`, `clients/*/.secrets/*`, `ssh-keys/`, `credentials/`.
- `.gitignore` must keep out: `ssh-keys/`, `credentials/`, `*.keystore`, `*.apk`, `*.tar.gz`, `**/secrets.h`, `**/wa.properties`, `.env*`,
  `**/build/`, `node_modules/`, `.secrets/`, `clients/Almanac/dist/`, `clients/Almanac/www/`, `clients/Almanac/android/app/src/main/assets/public`.
- Never `git add -A` blindly in this folder; check `git status` for secrets and large binaries first.

## Hardware gotchas

- Robot motors need the 2×18650 pack; AA cells only twitch. The ESP32 should sit on its own USB power bank.
- ENA/ENB jumper caps force full speed; remove them so PWM works.
- HC-SR04 ECHO must go through a voltage divider (5 V → 3.3 V).
- LD2410C needs 5 V; blind zone ~0.5 m; far or outside its ±60° cone it reads "nobody".
- The AV box is on a weak WiFi link (about −72 to −94 dBm): brief offline periods are normal.

## Software gotchas

- **Stale data from offline devices** (Tuya, retained MQTT values). Always check `online` and the age of the reading.
- `get_room_state` name collision (use `esp_status`).
- Git Bash: heredocs mangle `\n` in code strings; ESP-IDF/ESPHome builds need PowerShell.
- `npm run sync` (Capacitor) often exceeds the shell timeout: copy `www/` into `android/app/src/main/assets/public` directly (file 03).
- Capacitor needs Kotlin 2.x in the Almanac Android project; a Kotlin plugin pinned to 1.9.x breaks it.
- A published Almanac WebSocket has a 60-message / 10 s limit for normal frames and 250 / 10 s for robot frames.
- Android may kill the Phone Agent on Vivo/Funtouch unless Autostart and "allow background power" are set; Android 15 limits `dataSync`
  foreground services (we use `specialUse`).
- Two clients with the same MQTT `client_id` kick each other off: every service uses a fixed unique id (`layla-almanac-body`,
  `layla-home-bridge`, `layla-esp-plugin`, `layla-robot-001`, `layla-esp1`, ...). Never run a second copy.
- Postgres: the app role cannot do DDL; tests inside the container's `psql -U layla_app` use the trust socket, so verify passwords over TCP `127.0.0.1:55432`.

## Style of work the owner prefers

Replies in Telugu/Tenglish, short and clear, step-by-step lists; wants honest statements ("verified" vs "not tested"); dislikes repeated
APK builds; wants things production-ready, with backups and tests; money is tight, so avoid paid services unless asked.
