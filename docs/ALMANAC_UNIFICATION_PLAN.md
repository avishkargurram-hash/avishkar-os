# Almanac Unification Plan (2026-10-21)

Goal: ONE app -- **Almanac** (the product being sold) -- that also contains Layla Remote (GR joysticks),
the AV Box, Layla Voice and the Layla Phone Agent. Voice + Remote live under the **More** tab.
Status: PLAN ONLY. No code written for this yet. Implement with Opus, phase by phase.

## 1. Verified current state (read from the repo, 2026-10-21)

| Piece | Where | Tech | Notes |
|---|---|---|---|
| Almanac app | `clients/Almanac` | Capacitor 8 WebView, HTML/JS (`index.html` + `js/m-*.js`), appId `in.tryvanta.almanac`, compile/target SDK 36 | Modules self-register via `ALM.reg({id,title,group,render,...})`; More tab groups = `ALM.GROUPS` (Everyday / Planning / Private vaults / Live & family) in `js/m-core.js` |
| Almanac server | `layla/python/layla_almanac` (live: `layla-almanac.service`, port 8150) | stdlib HTTP + SQLite, WSS at `/api/almanac/ws`, header `X-Layla-Secret` (owner / tool / member tokens) | Already has the WebSocket hub + owner auth we need for robot control |
| **Priya <-> Almanac** | brain plugin `layla/brain-plugins/layla_almanac_bridge.py` + `layla365/l365/duties.py` | tools `almanac_today / almanac_add / almanac_mark_done / almanac_changes`; Priya duty `almanac_watch` every 5 min (change feed), day plan 14:00, evening 21:00 | **Connected by design ("Priya owns the Almanac, through Layla").** NOT re-verified live today -- first Opus task is a read-only check of `core` last_run for `duty:almanac_watch` + one `almanac_add` round-trip |
| Layla Phone Agent | `clients/LaylaPhoneAgent` | native Kotlin: AccessibilityService, NotificationListener, foreground service (specialUse), boot receiver, call/SMS/contacts perms; compile/target **36** | Same SDK level as Almanac -> mergeable |
| Layla Voice | `clients/LaylaVoice` | native Kotlin: BT audio router, continuous recorder, foreground service (microphone); compile/target **33** | Must be raised to 36 on merge |
| Layla Remote | `clients/LaylaRemote` (built 2026-10-21) | native Kotlin joysticks + Paho MQTT **direct to broker with the tvrobot password baked in** | Works on the real robot. To be replaced by an Almanac module that does NOT carry the password |
| LaylaCarFace | `clients/LaylaCarFace` | kiosk WebView | **Stays separate.** It is the robot's own head screen (the Android unit mounted on GR): must auto-boot into Layla's face with no menu |
| AV Box | brain plugin `layla/brain-plugins/layla_esp.py` | ESPHome box, tools esp_status/esp_history/esp_display/ir_learn/ir_send/ir_list/ir_forget | Reads broker 127.0.0.1:51883 |

## 2. Target architecture

```
Almanac (phone)  --HTTPS/WSS-->  nginx  -->  layla_almanac :8150  --(local, anonymous)-->  mosquitto 127.0.0.1:51883  -->  ESP32 (GR)
   More > Layla group                         owner-token auth                                                   ^
   ( Robot, AV Box, Voice, Phone )            /robot/*  + WS channel                                  brain plugin layla_robot.py
                                                                                                      (voice: "Layla, move forward")
                                                       shared module: layla_robot_core.py (publish drive/stop, read telemetry)
```

Rules:
- The phone NEVER holds an MQTT password. Auth = the existing Almanac owner token.
- One robot driver (`layla_robot_core.py`) shared by the Almanac server routes and the brain plugin, so voice and joystick follow identical safety rules.
- Joystick stream uses the existing `/api/almanac/ws` (low latency, telemetry pushed back: robot online, motor state, obstacle, distance).
- Everything under the new "Layla" group is hidden unless the owner token is present (`A.visible` gate). Family member tokens must never see it.

## 3. Build strategy -- UPDATED 2026-10-21: owner-only for now, ONE build

Owner decision: P0-P4 approved, and **this app is for the owner only right now** ("idi naaku matrame sontham"). So: build ONE app with everything
(all permissions, no hesitation), no flavor split yet. Selling to others is a LATER decision. To keep that door open cheaply:
- put every Layla-only screen behind the existing `A.visible` gate + one `OWNER_BUILD` constant, so a customer variant later is a flag, not a rewrite;
- keep the Phone Agent / Voice code in separate library modules (not tangled into Almanac's web code).

Development safety (the owner's real vault/passwords data lives in this app): build and test the merged app as a **separate dev app**
(`applicationId` suffix `.dev`, own data) until each phase is proven on the real phone; only then ship it over the real `in.tryvanta.almanac`.
Take an Almanac data export/backup before the first native merge; keep the last known-good APK installable.

### (Deferred) customer-vs-owner flavors -- only if/when Almanac is sold
Almanac customers must not receive an app that asks for AccessibilityService, SMS, call-log and mic-always permissions.
Use Gradle product flavors in `clients/Almanac/android`:

| Flavor | applicationId | Contains |
|---|---|---|
| `almanac` (customer) | `in.tryvanta.almanac` | web modules only (today's app) |
| `layla` (owner) | `in.tryvanta.almanac.layla` | everything: + Robot, AV Box, Voice, Phone Agent |

Different applicationIds so both can be installed. Sideload only (APK download page already exists); do not target Play Store with the `layla` flavor.

## 3b. Progress log
- **2026-10-22 P0 backend DONE + deployed** (Opus):
  - Priya<->Almanac verified LIVE: `duty:almanac_watch` ran 543x in 2 days, reading rev 13, never "unavailable".
  - `layla_almanac/mqtt.py` (stdlib MQTT 3.1.1 client; system python has no paho) + `layla_almanac/body.py` (robot + AV box;
    physical directions; fw<2 auto-swaps forward/backward; dead-man 0.6 s; 600 ms bursts re-sent every 0.25 s; voice moves
    capped 5 s; front stop <20 cm from fresh distance; refuses drive when robot reports offline; owner-only).
  - Routes (owner token only, family/tool tokens -> 401): `GET /api/almanac/body/state`, `POST /robot/drive {action,speed,seconds?}`,
    `/robot/stop`, `/robot/config {invert_fb:null|bool, invert_lr}`, `/avbox/ir {op:send|learn|forget,name}`, `/avbox/display {text}`,
    `/avbox/switch {id,on}`. WS (owner): `robot.drive {a,s}`, `robot.stop`, `body.get`; server pushes `{"t":"body",...}`;
    robot frames have their own 250/10 s budget; a vanished driving socket triggers stop. nginx needed no change.
  - Brain: new plugin `layla_robot.py` (robot_move / robot_stop / robot_status -> Almanac API, token from almanac.env,
    kill switch LAYLA_ROBOT=0), registered in layla_service.py (tuple loop + `_cap_init("layla_robot")`).
    `layla_esp.py` now serves `layla/esp1/ir/request` -> `ir/result` and retains the button-name list on `ir/catalog`.
  - Verified live: AV box readings flow (29.5 C / 60 %), IR round trip Almanac->brain->Almanac, voice plugin status,
    offline refusal, public unauth 401. Tests 71/71 (51 old + 20 new). Backups: `/opt/layla-almanac.bak.body.1792609519.tgz`,
    `/opt/layla/*.bak.robot.1792609564`.
  - Firmware v2 written: `clients/LaylaGR-firmware/LaylaGR/LaylaGR.ino` (+ gitignored `secrets.h`). Compiles clean with
    arduino-cli (esp32:esp32:esp32, core 2.0.17, 66% flash). NOT flashed yet -- owner flashes from Arduino IDE.
- **2026-10-22 P1 web modules DONE (in the APK, not yet on the phone)**:
  - `clients/Almanac/js/m-layla.js` (new): More > "Layla" group with **Layla GR** (two pointer-event joysticks, multi-touch,
    big Stop, top-speed slider, forward/back calibration Auto/Swapped/As-wired, swap L/R, live chips) and **AV Box**
    (sensor tiles, switches if any, IR buttons tap-to-send, forget sheet, teach-a-button, OLED message). Owner only.
  - Small hooks: `m-infra.js` forwards unknown WS messages via `A.fire('ws', m)` and state via `A.fire('wsState')`;
    `m-core.js` adds the `layla` group + robot/sensor icons; styles appended to `css/modules.css`.
  - Verified in headless Chromium against a local server with a fake robot (no MQTT): group + tiles render, chips show,
    a forward push sends ~1 drive every 0.36 s (fw1 -> "backward"), release sends stop, AV tiles/IR buttons render, no JS errors.
  - Background syncs no longer rebuild an open Robot/AV page (sticks would jump, typed text would vanish).

## 4. Phases (do in order; each ends with a test the owner can feel)

**P0 - Backend foundation (no app change).**
1. `layla_robot_core.py` + brain plugin `layla_robot.py` (tools: robot_drive, robot_stop, robot_state; later robot_look). Mock-MQTT unit tests.
2. Almanac server: owner-only `POST /robot/drive`, `POST /robot/stop`, `GET /robot/state`, WS message types `robot.drive` / `robot.telemetry`. Server-side dead-man: if no drive frame for 600 ms, publish stop.
3. AV Box routes: `GET /avbox/state`, `GET /avbox/history`, `GET /avbox/ir`, `POST /avbox/ir/send`.
4. **Firmware v2** (owner flashes once): flip motor directions in code, delete the IR gate, add HC-SR04 (TRIG 5 / ECHO 19 via divider) -> `distance/state` + stop when the FRONT is < ~20 cm, move ENA/ENB back to PWM, replace the fixed `duration_ms` model with a dead-man (stop if no command for 600 ms), keep `MAX_MOVE_MS` only as a ceiling.
   Acceptance: voice + curl both drive the robot; unplugging the phone's network stops it within ~1 s.

**P1 - Almanac web modules (Remote + AV Box).**
- Add group `['layla','Layla']` to `ALM.GROUPS`; modules `robot`, `avbox`.
- `robot`: two touch joysticks (Pointer Events, multi-touch), speed from stick distance, STOP, F/B and L/R flip toggles (prefs), telemetry chips (robot online, motor, obstacle, distance).
- `avbox`: live tiles (temp, humidity, light, motion), history sparkline, IR buttons from `ir_list` (tap = `ir_send`), "learn a new button" flow, on/off where the box exposes it.
- Build with `npm run sync`. Acceptance: drive GR from the Almanac `layla` APK on the real robot, identical feel to LaylaRemote.

**P2 - Phone Agent into Almanac (native).**
- Convert `LaylaPhoneAgent` to an Android library module included only by the `layla` flavor; add a Capacitor plugin `LaylaPhone` (status, start/stop service, request permissions, open accessibility settings, battery-whitelist prompt, last action log).
- More > "Phone agent" screen = permission checklist + on/off + recent actions.
- Carry over known traps (see memory `layla-phone-agent-tier2`): MQTT client_id collision, Funtouch kill-loop, Android 15 foreground-service time limits (specialUse).
- Acceptance: call / SMS / WhatsApp commands from Layla still work with Almanac as the only app installed.

**P3 - Voice into Almanac (native).**
- Library module from `LaylaVoice` (raise compile/target 33 -> 36, keep `foregroundServiceType=microphone`), Capacitor plugin `LaylaVoice` (start/stop pods mode, BT device state, transcript events).
- More > "Layla Voice" screen (web UI over the plugin) replacing `UiViews.kt`.
- Acceptance: Bluetooth earbuds -> continuous capture -> Layla reply, with the screen off.

**P4 - Release + cleanup.**
- Sign with `app/layla_release.keystore`, publish `Almanac-layla.apk` next to the existing download, run old apps in parallel ~1 week, then retire LaylaVoice / LaylaPhoneAgent / LaylaRemote. Keep LaylaCarFace.
- Rotate: tvrobot MQTT password, WiFi password, esp1 MQTT password (all were pasted in chat); remove the password from LaylaRemote's `.secrets` after retirement.

## 5. Risks / watch-outs
- Merging native Kotlin into a Capacitor project: manifest merge conflicts (permissions, services), dependency version clashes, `in` is a Kotlin keyword -> package decls need backticks.
- Android 14/15 foreground-service limits and OEM (Funtouch) kill behaviour -- needs a real-phone soak test, not an emulator.
- WebView joystick latency over WSS: measure; fall back to batched 20 Hz frames.
- Build RAM: this PC has ~3 GB free; kill stray java/node daemons first, use `--no-daemon`, ignore the harmless "Could not connect to Kotlin compile daemon" trace.
- Family members must never see the Layla group or reach `/robot/*`.

## 6. Facts learned on the robot today (do not rediscover)
- Root causes of "robot won't move": IR gate on a floating/removed GPIO23 (tie GPIO23 to 3V3 until firmware v2), `MAX_MOVE_MS=2000` silently rejects longer commands, 4xAA too weak through L298N -> **2x18650 (7.4V) fixed it**.
- Motors are wired so firmware `backward` = physically forward (firmware `forward` = reverse and was the IR-gated one). Remote app has an F/B flip toggle; firmware v2 should fix it at the source.
- Pin map: IN1 26, IN2 27, IN3 14, IN4 12, ENA 25, ENB 13, IR 23, PIR 32, servo 18, TRIG 5, ECHO 19 (IN4=12 and TRIG=5 are strapping pins).
- No mosquitto clients on the VM host: use `sudo docker exec genesis-data-mosquitto-1 mosquitto_pub/sub -h 127.0.0.1 -p 1883` (local, anonymous). Public TLS: `layla.tryvanta.in:8883`, user `tvrobot`.
- ESP occasionally drops offline->online (suspected motor-current reset) -> add 1000 uF across the motor supply / near the ESP if it recurs.

## 7. Decisions
- DECIDED (owner, 2026-10-21): P0 through P4 all approved. Owner-only app for now; flavor split deferred (see section 3).
- RECOMMENDED, not yet answered: keep the LaylaRemote APK as a fallback until the Almanac Robot module is proven.
- OPTIONAL, not yet answered: a Priya card in Almanac (what she is watching / last digest).

## 8. "Make it the best" extras (cheap now because it is personal; do inside the phases)
1. Robot safety: server dead-man (600 ms), big always-visible E-stop, front stop from HC-SR04, low-battery/ESP-offline banner.
2. One sign-in: the owner token is entered once and shared by every module (Robot, AV Box, Voice, Phone Agent).
3. Always-on reliability: battery-optimisation whitelist prompt, boot autostart, a self-check that reports "Voice/Phone agent stopped" to Telegram (Layla already has a self-healing pattern in `layla_esp.py`).
4. A single "Layla status" tile on Home/More: brain, robot, AV Box, voice, phone agent -- green/red.
5. Almanac data backup/restore (export file) before any native merge.
