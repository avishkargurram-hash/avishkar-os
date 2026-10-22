# 04 — The Almanac app (web UI + Android shell + server)

## Layers

```
Android shell (Capacitor 8, package in.tryvanta.almanac)
 ├─ WebView:  clients/Almanac/index.html + js/m-core.js, m-planning.js, m-vaults.js, m-infra.js, m-layla.js + css/modules.css
 ├─ Native plugin  app.tryvanta.laylanative.LaylaNativePlugin   (Kotlin)   → JS name "LaylaNative"
 ├─ Library module :phoneagent  (source folder clients/LaylaPhoneAgent)     calls/SMS/contacts/accessibility/notifications
 └─ Library module :waagent     (source folder clients/LaylaWaAgent)        WhatsApp auto-reply listener
Server: layla/python/layla_almanac  (stdlib HTTP + SQLite + WebSocket)  on the Oracle VM, port 8150
```

The owner enters the Almanac owner token once in the app (tap the leaf icon, top-left); it is stored in the phone's local
storage (`almanac_sync_cfg`). The app talks to `https://layla.tryvanta.in/api/almanac/*`.

## Web modules (`ALM.reg({id,title,icon,desc,group,render,badge,chip,member})`)

- `m-core.js`: module registry, More hub, helpers (`A.head`, `A.toast`, `A.ask`, icons), groups in `ALM.GROUPS`:
  Everyday / Planning / Private vaults / Live & family / **Layla**.
- `m-infra.js`: native alarms, the **live WebSocket** (`RT`) used for clipboard, family and now robot/body telemetry
  (`A.fire('ws', msg)`), Family Connect.
- `m-layla.js`: everything added for Layla (owner only: no `member` flag):
  - `robot` — **Layla GR** two-stick joysticks (`RB`): left stick forward/back, right stick turn; speed curve squared, minimum
    PWM 90, `RAMP_MS` 400 soft start, turn speed = 80% of the top-speed slider; sends `robot.drive` frames over the WebSocket
    every ~250 ms, `robot.stop` on release; calibration (forward/back "Auto", swap left/right) stored on the server.
  - `avbox` (tile named "Bedroom") — dark-glass **Bedroom & Appliances** page (`AV`, CSS classes `hm-*`): sensors + radar
    Presence, fan dial, ceiling-light sliders, bulb/tube/general switches, plug, TV, "Connect later" placeholders (AC, geyser,
    smart switch, water motor, washing machine), **Auto-off automation card**, IR remote buttons, OLED message.
  - `phone` — **Phone & WhatsApp** (`PH`): permission checklist + WhatsApp kill switch. Only works inside the Android app.
- Telemetry model: the server pushes `{"t":"body", robot, avbox, home, presence}` over the WebSocket; the page keeps it in
  `LAYLA.body`. Re-renders triggered by background sync are made idempotent (`el.querySelector('#hmRoot')` etc.) so sliders and
  typed text are not destroyed.
- `body:has(#hmRoot)` darkens the whole page while the Bedroom screen is open and hides the normal top bar.

## Server routes added for Layla (all **owner token only**; family/tool tokens get 401)

| Route | Purpose |
|---|---|
| `GET /api/almanac/body/state` | Robot + AV box + home devices + presence snapshot |
| `POST /robot/drive {action, speed, seconds?}`, `/robot/stop`, `/robot/config {invert_fb, invert_lr}` | Drive (held or timed) / stop / calibration |
| `POST /avbox/ir {op: send/learn/forget, name}`, `/avbox/display {text}`, `/avbox/switch {id,on}` | IR remote, OLED, ESPHome switches |
| `POST /home/control {device, action, value}` | `device`: `fan`, `plug`, `tv`, `light:<bulb|tube|ceiling1|ceiling2|general>`; `action`: on/off/toggle/speed/dim/(tv keys) |
| `POST /home/refresh {force}` | Ask the brain to re-read the cloud devices |
| `POST /presence/config {enabled, empty_min, restore, fan, lights[]}`, `/presence/snooze {minutes}` | Presence automation |
| WebSocket messages | `robot.drive {a,s}`, `robot.stop`, `body.get` (client→server); `body` (server→client) |

Code: `body.py` (robot safety + AV box + home relay), `presence.py`, `mqtt.py` (tiny stdlib MQTT client — the VM Python has no paho),
`server.py` (routes/WebSocket), `__main__.py` (wiring; env `ALMANAC_BODY=0`, `ALMANAC_PRESENCE=0` disable parts).

### Robot safety rules (in `body.py`, every caller shares them)
Motor commands are short bursts (600 ms) that expire by themselves in the firmware; the server dead-man stops a held drive if
not refreshed within 0.6 s; voice moves are capped at 5 s; physical-forward is refused when a fresh distance reading is
< 20 cm; driving is refused when the robot reports offline; a WebSocket that was driving and disconnects triggers a stop.
Directions in the API are **physical**; firmware `fw < 2` has forward/back swapped (the server compensates), `fw ≥ 2` does not.

### Home relay
The Almanac server cannot reach the cloud devices (Tuya, Evolviot) itself. It publishes to MQTT `layla/home/request`; the brain
plugin `layla/brain-plugins/layla_home.py` executes it using the brain's existing read-back-verified tools and answers on
`layla/home/result`, and keeps a retained snapshot on `layla/home/state`. **A fan/plug that Tuya says is offline is returned as
an error with the reason** (never as "on").

### Presence automation (`presence.py`, default OFF)
Acts only if: radar AND PIR both say empty for `empty_min` minutes (default 10), the AV box is online with fresh readings, the radar
has seen someone within 12 h, not snoozed, once per absence; only devices currently on; lights + optional fan; never the plug or TV;
optional restore-on-return. It publishes `layla/home/event`, which the brain forwards as a push notification.
Config persists in the hub's `hub_meta` table (`presence_cfg`, `robot_cfg`).

## Android native pieces

- `android/settings.gradle` includes `:phoneagent` and `:waagent`; their `build.gradle` + trimmed `AndroidManifest.xml` live in
  `android/phoneagent/` and `android/waagent/` and point `srcDirs` at the original client folders (single source of truth; the
  standalone Phone Agent / WhatsApp apps still build from their own folders). Library manifests have no launcher and no
  `<application>` attributes.
- `android/build.gradle` classpath: `kotlin-gradle-plugin:2.2.20` (Capacitor 8's plugins need Kotlin 2.x). `kotlin { compilerOptions { jvmTarget } }`
  must be a top-level block (app: JVM_21, libraries: JVM_17).
- `MainActivity.java` registers the plugin **before** `super.onCreate`.
- Plugin methods: `status`, `startPhone`, `stopPhone`, `askPermissions`, `openSettings{target}`, `waStatus`, `waPower{on}`.
  The WhatsApp device token never reaches JavaScript.
- Two separate Notification Listener services exist (`LaylaNotificationListener`, `WaListenerService`); the owner enables both in
  Android "Notification access". `WaListenerService.WA_PACKAGES` = `com.whatsapp` + `com.whatsapp.w4b`.
- Phone Agent runs a foreground service (`specialUse` type, because Android 15 caps `dataSync` at 6 h/day) and needs: runtime
  permissions, Accessibility, Notification access, battery-optimisation exemption, overlay permission. On Vivo/Funtouch phones also
  Autostart + background power allowance.
- Permissions merged into the app (24 total) include CALL_PHONE, SEND/READ/RECEIVE_SMS, READ_CONTACTS, READ_CALL_LOG,
  QUERY_ALL_PACKAGES, SYSTEM_ALERT_WINDOW. This is a **sideloaded personal build**; do not publish this variant to Play Store.

## If you ever sell Almanac to other people
Create a second build variant without the Layla-only parts: no Phone/WhatsApp libraries or permissions, and hide the `layla`
module group (`A.visible` / an `OWNER_BUILD` flag). Family-member tokens already cannot reach any Layla route.
