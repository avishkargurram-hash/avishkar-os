# 05 — Robot, AV box and home devices

## Layla GR robot

**Hardware:** ESP32 DevKit V1, L298N motor driver, 4 TT gear motors, **2 × 18650 (7.4 V) in a 2-cell holder on L298N +12V/GND**
(4×AA was too weak and was the original reason it "only twitched"), HC-SR04 ultrasonic on the front, PIR, SG90 servo (not used yet),
an Android head-unit (9") as the face running `clients/LaylaCarFace` (kiosk of `https://layla.tryvanta.in/app`; the unit has no
microphone/speaker of its own — a USB speakerphone is recommended). The ESP32 is powered by a USB power bank (separate from the
motor pack). All grounds common. L298N 5V-EN jumper stays ON (7.4 V is enough for its regulator); ENA/ENB are wired to GPIO25/13
(PWM) with **no** jumper caps (caps would force full speed).

**Pins:** IN1 26, IN2 27, IN3 14, IN4 12, ENA 25, ENB 13, HC-SR04 TRIG 5 / ECHO 19 (echo through a 1k/2k divider), PIR 32, servo 18.
(GPIO12 and GPIO5 are strapping pins; fine so far.)

**Firmware v2** (`clients/LaylaGR-firmware/LaylaGR/LaylaGR.ino`): WiFi + TLS MQTT to `layla.tryvanta.in:8883` as user `tvrobot`;
commands on `tryvanta/robot/001/motor/set` as `{"action":"forward|backward|left|right|stop","speed":0-255,"duration_ms":1-2000}`;
motors auto-stop when `duration_ms` ends or WiFi drops; forward is blocked when the sonar sees < 20 cm (2 consecutive readings);
publishes `status` (LWT), `fw` (=2), `ip`, `motor/state`, `distance/state`, `obstacle/state`, `pir/state`. ArduinoOTA host `layla-gr`
(password in `secrets.h`). Physical wiring made firmware v1's "FORWARD" drive the robot backwards, so **v2 swapped the IN pin
patterns in code** (left/right unchanged); `fw=2` tells the Almanac server not to compensate any more.

**Speed calibration (owner-tested):** below PWM ~90 the TT motors on 7.4 V stall/hum; ≥140 is "racing car". Defaults: min 90,
top-speed slider 100–255 (default 170), squared stick curve, 400 ms ease-in, turns at 80% of top speed. Voice default 110.

**How it is controlled:** Almanac joysticks → WebSocket → Almanac server (`body.py`) → local MQTT. Layla's voice tools
`robot_move / robot_stop / robot_status` (`layla/brain-plugins/layla_robot.py`) call the same HTTP routes, so voice and joystick
share the safety rules. The old standalone `clients/LaylaRemote` APK talks to the broker directly with a baked password; it is a
fallback only and can be deleted once the Almanac module is trusted.

**Known quirks:** the ESP sometimes dropped offline→online when motors started on the AA pack (brown-outs); less likely on the
18650 pack — if it returns, add a 1000 µF capacitor across the motor supply and near the ESP.

## AV Box (ESPHome, `C:\Users\Administrator\esphome\sensors.yaml`, device name `sensors`)

ESP32 + DHT22 (temp/humidity, GPIO4), LDR (GPIO34, raw volts, scale not calibrated), PIR (GPIO26), IR obstacle (GPIO35), IR transmitter
LED (GPIO23), IR receiver (GPIO27, Pronto codes), SSD1306 OLED (I²C 21/22), **HLK-LD2410C mmWave radar** (UART RX16/TX17, 256000 baud,
5 V). IP `192.168.29.186` (static via `use_address`), MQTT prefix `layla/esp1`, broker TLS with the ISRG Root X1 CA embedded.
Radar entities: presence / moving target / still target (binary) and distances (cm) and energies (0–100). The radar sees a person who sits
perfectly still (PIR cannot). In ESPHome 2026.8 the `ld2410:` option `throttle:` no longer exists. The box is on weak WiFi at a temporary
location; offline gaps are expected (the brain's `_healer` only sends a gentle note after 15 min).

Brain plugin `layla/brain-plugins/layla_esp.py` (tools `esp_status`, `esp_history`, `esp_display`, `ir_learn/ir_send/ir_list/ir_forget`):
keeps rolling history in memory, answers "is anybody in the room" with the radar, and serves the Almanac IR requests
(`layla/esp1/ir/request` → `ir/result`, button names retained on `ir/catalog`). Learning IR needs the receiver; **sending needs the
IR LED firmware (already in the YAML)** and a clear line of sight.

## Home devices

| Device | Cloud / path | Notes |
|---|---|---|
| **Bedroom fan** — Tuya "Fan-Modular Switch" `d7be5923733cd5bd80zdqi`, DPs `switch`, `fan_speed_percent` (1–5) | Tuya Cloud API via `tinytuya` (India data center, project credentials in `/opt/layla/.env`) | **Offline since 2026-10-09.** Re-pair in Smart Life when at home. The adapter now returns an error with the reason when the device is offline |
| **Smart plug** — Wipro 16A `d798cfe474a005b89cyjci`, switch DP is `switch_1`, power `cur_power` (0.1 W) | Tuya Cloud | Online |
| **Lights** — Evolviot SW5R0T5 5-channel module | Evolviot cloud REST (`api.evolviot.com`, OAuth device-code pairing; tokens in `/opt/layla/evolviot_tokens.json`) | Channels are named "Switch 1..5" in the app; **assumed mapping** switch1=bulb, switch2=tube, switch3=ceiling light 1, switch4=ceiling light 2, switch5=general (`LIGHT_ROLES` in `layla_home.py`). Channels 3–5 are dimmable. Every command is verified by reading the state back |
| **TV** — Google TV SWTV-22AE | ADB over the home LAN through a bridge script on the owner's laptop (`C:\Users\Administrator\layla-bridges\tv_adb_bridge.py`, scheduled task "LaylaBridges") | Works only when the laptop, the bridge and the TV (Network-ADB app, RSA authorised) are up; IP drifts (find by MAC). Replies honestly when the bridge is silent |

**Tuya IoT Core trial:** the developer project (iot.tuya.com → Cloud → Development → project → Service API → IoT Core) is a free
trial that expires; when it does the API returns `Err 913 "IoT Core service subscription has expired"` and fan + plug stop
working although the Smart Life app still works. Renew with "Extend Trial Period" (form: Individual Developer, ~2 devices,
personal project). **Extended on 2026-10-22 for 3 months → renew again around mid-January 2027.** Do not click "Subscribe to
Resource Pack" (paid).

**Planned / not connected yet ("Connect later" tiles):** air conditioner, geyser, smart switch, water motor, washing machine.
To add a Tuya device without asking the owner: it only has to be paired in the same Smart Life account; list the project's
devices with `tinytuya.Cloud(...).getdevices()` and read real DP codes with `getstatus(id)` — never guess DP codes.
