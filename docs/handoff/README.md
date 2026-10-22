# Layla / Avishkar-OS — Handoff Guide

Written 2026-10-22 for the owner (Avishkar) and for any AI assistant (Gemini, ChatGPT, Claude, ...) that continues the
work while Claude is unavailable. **Read this file first, then the numbered files in this folder.**

## What this system is

One person's personal AI "operating system", named **Layla**, plus a product built on top of it:

| Part | What it does | Where it lives |
|---|---|---|
| **Layla brain** | The assistant: chat, voice, tools (home, phone, WhatsApp, research...) | Oracle VM `129.225.72.80`, service `layla-brain`, port 8100 |
| **Almanac app** | The owner's Android app (planner, vaults, family, + robot, bedroom, phone controls). Also the product being sold. | `clients/Almanac` (web UI in Capacitor) + server `layla/python/layla_almanac` |
| **Layla GR robot** | 4-wheel robot with an Android screen for a face | firmware `clients/LaylaGR-firmware`, controlled through Almanac |
| **AV Box** | ESP32 sensor box: temperature, humidity, light, PIR, **LD2410C radar**, IR remote, OLED | ESPHome config `C:\Users\Administrator\esphome\sensors.yaml` |
| **9 agents** (Priya, Nitya, Megha, ...) | Autonomous daily workers that report to Telegram | server `tv-mum-01`, service `l365-runner` |
| **Scientist OS** | Research engine (Megha uses it) | `tv-mum-01`, `sci-api` port 8095 |
| **Layla portal** | Subscription site `layla.tryvanta.in/subscribe` (Cashfree payments, coupons) | Oracle VM, service `layla-portal`, port 8160 |
| **WhatsApp agent** | Auto-replies to people NOT saved in contacts | server `layla-wa` (8120) + phone code merged into the Almanac APK |
| **Phone agent** | Calls/SMS/contacts/app-control from Layla | `clients/LaylaPhoneAgent`, merged into the Almanac APK |

## The five rules that keep you out of trouble

1. **Never print, paste, commit or send a secret.** Secrets live only in gitignored files and server `.env` files (see
   `02_SYSTEM_MAP.md`, section "Where secrets live"). If you must show a config, mask values (`sed 's/=.*/=<hidden>/'`).
2. **Back up before you edit anything on a server** (`cp file file.bak.<what>.<timestamp>`) and run the tests first.
3. **Two things are deliberately OFF and only the owner turns them on:** WhatsApp auto-reply (Telegram `/wa on` or the
   Almanac switch) and Presence auto-off (Almanac → Bedroom → Automation). Do not enable them yourself.
4. **Do not rebuild/send the Android APK for small changes.** The owner dislikes repeated APKs. Batch changes, test the
   web part in a headless browser, build one APK at the end.
5. **Never trust an old reading.** Several devices report their last value forever after going offline. Check the
   `online` flag / age of data before saying "it is on".

## Current state at handoff (2026-10-22)

| Item | State |
|---|---|
| Robot firmware v2 (HC-SR04 front stop, WiFi OTA, directions fixed in firmware) | Flashed and running |
| Almanac APK with Robot + Bedroom + Presence + Phone & WhatsApp | Built and sent to the owner (installed over the old one) |
| Tuya IoT Core trial | Extended 3 months on 2026-10-22 → **renew again by ~2027-01-15** or fan/plug stop working |
| Fan switch (Tuya "Fan-Modular Switch") | **Offline since 2026-10-09** (lost WiFi). Owner away. Needs re-pairing in Smart Life when home |
| Smart plug (Tuya) | Online |
| Evolviot lights | Online |
| WhatsApp auto-reply | OFF (owner decides) |
| Presence auto-off | OFF (owner decides) |
| Layla portal coupons | Two launch coupons (a 50% one and a 100% waiver) exist until 2026-11-19; the codes are in the `tenancy.coupons` table, **never write them in docs or git** |
| Passwords pasted in chat earlier | **Not rotated** (owner chose to skip). See `06_OPEN_ITEMS.md` |

## Files in this folder

| File | Read it when |
|---|---|
| `01_HOW_TO_WORK_WITH_AN_AI.md` | You are about to ask an AI for help — copy the prompt pack |
| `02_SYSTEM_MAP.md` | You need to know which server/service/port/path/topic does what |
| `03_RUNBOOK.md` | You need to deploy, restart, roll back, flash, test or build |
| `04_ALMANAC_APP.md` | You are changing the Almanac app or its Android native parts |
| `05_ROBOT_HOME_DEVICES.md` | Robot, AV box, lights, fan, plug, TV, radar |
| `06_AGENTS_WHATSAPP_PORTAL.md` | The 9 agents, WhatsApp rules, subscription portal |
| `07_OPEN_ITEMS_AND_GOTCHAS.md` | You wonder what is unfinished or why something strange happens |

Related older docs: `docs/ALMANAC_UNIFICATION_PLAN.md` (the merge plan and progress log), `ARCHITECTURE.md`, `DECISIONS.md`.
