# 01 — How to work with an AI assistant on this project

The system is big and spans two servers, an Android app, two ESP32 devices and several services. An AI that does not
know the layout will guess and break things. Always give it context first.

## Step 1 — give the AI this opening message (copy/paste)

```
You are helping me maintain "Layla / Avishkar-OS", my personal AI system. Before doing anything:
1. Read docs/handoff/README.md and the file(s) for the area we are touching (02..07 in docs/handoff/).
2. Never print, paste or commit secrets. Mask values in any config you show me.
3. Before editing any file on a server, make a timestamped backup, and run the existing tests afterwards.
4. Do not build or send an Android APK unless I ask. Batch changes.
5. Never enable WhatsApp auto-reply or Presence auto-off; only I do that.
6. If a device shows a value, check whether the device is ONLINE and how old the reading is before trusting it.
7. Tell me what you will change and why before changing production. Prefer small, reversible changes.
Today's task: <describe it>
```

## Step 2 — what to attach, by task

| Task | Attach / point the AI at |
|---|---|
| Almanac screen or behaviour | `docs/handoff/04_ALMANAC_APP.md`, `clients/Almanac/js/m-layla.js` |
| Almanac server (robot, home, presence, WhatsApp switch) | `layla/python/layla_almanac/` and its tests |
| Robot firmware | `docs/handoff/05_ROBOT_HOME_DEVICES.md`, `clients/LaylaGR-firmware/LaylaGR/LaylaGR.ino` |
| AV box (sensors/IR/radar) | `C:\Users\Administrator\esphome\sensors.yaml`, section "AV Box" in file 05 |
| Agents (Nitya, Priya...) | `docs/handoff/06_AGENTS_WHATSAPP_PORTAL.md`, `layla365/l365/duties.py` |
| WhatsApp rules | `layla/python/layla_wa/engine.py` and `tests/test_wa.py` |
| Subscription / coupons | file 06, section "Portal" |

## Step 3 — prompt pack for common jobs

**"Something stopped working" (diagnose first, change nothing)**
```
Something is wrong: <symptom>. Do NOT change anything yet. Using docs/handoff/03_RUNBOOK.md (section "Health
checks"), list the exact read-only commands to find which part is broken, run them, and tell me the root cause with
evidence. Then propose the smallest fix and wait for my OK.
```

**"Change a rule in an agent or in WhatsApp"**
```
I want to change: <rule>. Find the code that decides it, show me the current logic, write the change, add or update a
unit test that proves the new behaviour AND a test that proves the old safety rules still hold, run the whole test
suite for that package, then show me the diff before deploying. Deploy only after I say yes, with a backup first.
```

**"Update the robot firmware"**
```
Edit clients/LaylaGR-firmware/LaylaGR/LaylaGR.ino as follows: <change>. Compile with arduino-cli (see runbook section
"Robot firmware"). Do NOT flash until I confirm the robot is on the floor/stationary and powered. Flash over WiFi (OTA);
USB only as a fallback. Afterwards read the MQTT topics to confirm fw version and sensors.
```

**"Add something to the Almanac app"**
```
Add <feature> to the Almanac app as a new module in clients/Almanac/js/m-layla.js (or a new m-*.js file), following the
existing module pattern (ALM.reg). Test it in the headless-browser harness (see 04_ALMANAC_APP.md, "Testing the web
part"). Do not build the APK; tell me when the web part is verified and list what the APK will contain.
```

**"Everything is fine, just make the final APK"** (only when the owner asks)
```
Build one Almanac debug APK following docs/handoff/04_ALMANAC_APP.md "Building the APK", verify it (signature, package
name, version code unchanged, merged classes present), then give me the file path.
```

## Things AIs commonly get wrong here (tell them up front)

- **`in` is a Kotlin keyword.** Package names starting with `in.` need backticks in Kotlin (`package \`in\`.tryvanta...`).
- **Capacitor 8 needs Kotlin 2.x.** Do not pin the Kotlin Gradle plugin to 1.9.x in the Almanac Android project.
- **Capacitor `Plugin` already has `requestPermissions`.** Do not name a method that.
- **Windows Git Bash mangles `\n` inside heredoc'd Python/C strings** and Bash cannot run ESP-IDF builds. Use PowerShell for
  ESPHome/ESP-IDF builds and write source text with an editor tool, not with echo/heredoc.
- **`get_room_state` is shadowed** by an old function of the same name in `layla_service.py`; the AV-box tool is `esp_status`.
- **Tuya returns stale data for offline devices.** Always check `online`.
- **The VM `ubuntu` user cannot `cd /opt/layla`.** Use absolute paths with `sudo -n`.
