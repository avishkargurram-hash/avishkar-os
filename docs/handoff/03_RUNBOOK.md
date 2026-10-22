# 03 — Runbook: how to do things

All server commands below assume you are in the repo root `Avishkar-OS/` in Git Bash on the owner's PC. Use absolute
paths on servers. Replace `<TS>` with `$(date +%s)`.

```bash
VM="ssh -i ssh-keys/ssh-key-2026-09-15.key -o StrictHostKeyChecking=no ubuntu@129.225.72.80"
TV="ssh -i ssh-keys/tv-mum-01.key -p 3052 -o StrictHostKeyChecking=no root@103.168.22.202"
```

## 1. Health checks (read-only, do these first when something is wrong)

```bash
$VM 'for u in layla-brain layla-almanac layla-portal layla-wa; do echo $u $(systemctl is-active $u); done'
$VM 'curl -s http://127.0.0.1:8100/health; echo; curl -s http://127.0.0.1:8150/api/almanac/ping; echo'
$VM 'sudo -n docker ps --format "{{.Names}} {{.Status}}" | grep -E "mosquitto|postgres"'
$TV 'systemctl is-active l365-runner sci-api; curl -s http://127.0.0.1:8090/health | head -c 200'
# robot + AV box live data (15 s)
$VM "sudo -n docker exec genesis-data-mosquitto-1 timeout 15 mosquitto_sub -h 127.0.0.1 -p 1883 -t 'tryvanta/robot/001/#' -t 'layla/esp1/#' -v | grep -v debug | head -40"
# everything the Almanac server knows about the body, fan, plug, lights, presence (needs the owner token, read on the VM)
$VM 'TOK=$(sudo -n grep ^ALMANAC_TOKEN= /opt/layla-almanac/almanac.env | cut -d= -f2-); curl -s -H "X-Layla-Secret: $TOK" http://127.0.0.1:8150/api/almanac/body/state | python3 -m json.tool | head -80'
# logs
$VM 'sudo -n journalctl -u layla-brain -n 60 --no-pager'
```

Brain restarts take ~25 s to answer `/health`; the SSH connection often drops during a restart (exit code 7) — just reconnect
and poll `/health`.

## 2. Run the tests (always before deploying Python)

```bash
cd layla/python && python -m pytest -q layla_almanac/tests layla_wa/tests -p no:cacheprovider     # ~1 min
```
Currently: Almanac 85 tests, WhatsApp 52 tests, all passing.

## 3. Deploy backend code (Python) — pattern

```bash
# a) back up on the server, b) copy, c) compile, d) restart, e) verify
cd layla/python
tar -czf - --exclude=__pycache__ --exclude=tests layla_almanac | $VM "set -e; S='sudo -n'; \
  \$S tar -czf /opt/layla-almanac.bak.<what>.<TS>.tgz -C /opt layla-almanac/layla_almanac; \
  cat > /tmp/a.tgz; \$S tar -xzf /tmp/a.tgz -C /opt/layla-almanac; rm /tmp/a.tgz; \
  \$S chown -R laylacomms:laylacomms /opt/layla-almanac/layla_almanac; \$S systemctl restart layla-almanac"
```
Same shape for `layla_wa` (→ `/opt/layla-wa`). Brain plugins (`layla/brain-plugins/*.py`) are single files copied to
`/opt/layla/` (keep the owner/group of the existing file), then `systemctl restart layla-brain`. A new plugin must also be
registered in `/opt/layla/layla_service.py` (a tuple loop near line 3700 and a `_cap_init("<name>", ...)` line near 7700);
make a `.bak` of `layla_service.py` first. Agents' duties (`layla365/l365/duties.py`) go to
`tv-mum-01:/opt/layla365/app/l365/duties.py`, then `systemctl restart l365-runner`.

## 4. Roll back

Every deploy above leaves a backup: `*.bak.<what>.<timestamp>` next to the file, or `/opt/<svc>.bak.<what>.<ts>.tgz`.
Copy it back over the file and restart the unit. Android: install the previous APK over the new one (the version code is
deliberately unchanged so this works without uninstalling; **never uninstall the Almanac app** — local vault data is lost).

## 5. Robot firmware (ESP32, `clients/LaylaGR-firmware/LaylaGR`)

Tools: `arduino-cli` bundled with Arduino IDE at
`C:\Users\Administrator\AppData\Local\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe`
(ESP32 core 2.0.17, library PubSubClient). Run from **PowerShell**.

```powershell
cd "...\Avishkar-OS\clients\LaylaGR-firmware"
$cli = "C:\Users\Administrator\AppData\Local\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
& $cli compile --fqbn esp32:esp32:esp32 --output-dir "$PWD\build" LaylaGR
# over WiFi (preferred). IP: read MQTT topic tryvanta/robot/001/ip (was 192.168.29.222). Password = OTA_PASS_VALUE in secrets.h
& $cli upload -p <robot-ip> --protocol network --fqbn esp32:esp32:esp32 --input-dir "$PWD\build" --upload-field "password=<OTA password>"
# USB fallback: robot ESP32 appears as COM5 (CP210x)
& $cli upload -p COM5 --fqbn esp32:esp32:esp32 --input-dir "$PWD\build"
```
Robot must be switched on and on the same WiFi as the PC. It stops its motors when an OTA starts. After flashing, check
MQTT: `status online`, `fw 2`, `distance/state` numbers. Write C string literals (`"...\n"`) with an editor tool, not heredocs.

## 6. AV box firmware (ESPHome, `C:\Users\Administrator\esphome\sensors.yaml`)

```powershell
cd C:\Users\Administrator\esphome
& "C:\Users\Administrator\AppData\Local\io.esphome.builder\python\python.exe" -m esphome config sensors.yaml     # validate
& "C:\Users\Administrator\AppData\Local\io.esphome.builder\python\python.exe" -m esphome run sensors.yaml --device 192.168.29.186 --no-logs
```
**Must be PowerShell** (Git Bash fails with "MSys/Mingw is not supported"). First build ~15 min, later ones faster. The box is
at the owner's temporary home on weak WiFi; if it is offline just wait. Keep a copy of the YAML before edits
(`sensors.yaml.bak.*`; the folder is a git repo).

## 7. Android APK (Almanac) — only when the owner asks, one APK per batch

```bash
cd clients/Almanac
node --check js/m-layla.js js/m-core.js js/m-infra.js        # syntax
node scripts/copy-www.mjs                                    # builds www/
P=android/app/src/main/assets/public
cp www/index.html www/almanac.config.js $P/ && rm -rf $P/js $P/css && cp -r www/js www/css $P/   # (npm run sync often times out; this is equivalent)
cd android
export JAVA_HOME="/c/Program Files/Eclipse Adoptium/jdk-21.0.12.101-hotspot"; export PATH="$JAVA_HOME/bin:$PATH"
./gradlew assembleDebug --no-daemon -q          # output: android/app/build/outputs/apk/debug/app-debug.apk
```
- Free RAM first (this PC has ~3 GB): close Gradle/Kotlin daemons and Chrome; use `--no-daemon`. A "Could not connect to Kotlin
  compile daemon" stack trace is harmless if the build still ends with EXIT=0.
- Verify: `aapt dump badging` (package `in.tryvanta.almanac`, versionCode **1**), `apksigner verify`, and grep the dex for
  `laylanative/LaylaNativePlugin`, `laylaphone/PhoneAgentService`, `laylawa/WaListenerService`.
- Keep `versionCode 1` and the same debug signing key so it installs over the existing app and can be rolled back.
- The WhatsApp server URL/token are baked from the gitignored `clients/LaylaWaAgent/wa.properties`; without that file the
  WhatsApp section shows "no server settings".

## 8. Testing the Almanac web part without the phone

The UI can be exercised in headless Chromium (Playwright for Python is installed) against a **local** Almanac server with a
fake robot/box: start `layla_almanac.server.serve(...)` with a `Body` whose publish function just records messages, serve
`clients/Almanac` with `http.server`, put `{"url": "<local api>", "token": "<test token>"}` in `localStorage.almanac_sync_cfg`
and `almanac_mode=owner`, then `ALM.open('robot' | 'avbox' | 'phone')` and screenshot. For the Phone screen inject a fake
`window.Capacitor` (`isNativePlatform: () => true`, `registerPlugin: () => ({status..., waStatus..., waPower...})`).
Never point the harness at the production server.

## 9. Kill switches and "make it stop"

| What | How |
|---|---|
| Robot | Almanac → Layla GR → big **Stop**; server dead-man stops it within 0.6 s of lost link; switch off its battery switch |
| WhatsApp auto-reply | Telegram `/wa off` or Almanac → Phone & WhatsApp switch |
| Presence auto-off | Almanac → Bedroom → Automation toggle, or "Pause 8 h" |
| One of the 9 agents | Telegram/brain tool `pause_agent`; or `ALMANAC_PRESENCE=0` / `ALMANAC_BODY=0` in the Almanac service env to disable parts |
| Voice robot control | `LAYLA_ROBOT=0` in `/opt/layla/.env`, restart brain |
| All 9 agents' gateway | create the kill file configured as `KILL` in `layla_l365.py` |
