# 06 — The 9 agents, WhatsApp auto-reply, subscription portal

## The 9 autonomous agents ("Layla 365")

Runner `l365-runner` on **tv-mum-01** (`/opt/layla365/app/l365/`, duties in `duties.py`). Each agent wakes every ~30 s, does its
scheduled "duties", and **reports to the owner on Telegram**. Agents never touch devices directly: every action goes through the
brain's **gateway** (`layla/brain-plugins/layla_l365.py`, endpoint `/agent/gateway`) which checks the agent's token, an
allow-list of "verbs", argument validation and rate limits (per minute / per day; heartbeat and inbox polls are exempt from the daily
cap — that exemption fixed the 2026-10 "agents stopped reporting after ~1 pm" outage).

| Agent | Role | Duties (IST) |
|---|---|---|
| **Priya** | Life/health and **owner of the Almanac** | Day plan 14:00, evening wellness 21:00 (now includes room temperature/humidity), `almanac_watch` every 5 min (what changed in the Almanac) |
| **Nitya** | Home automation | `home_watch` every 30 min (24/7, no LLM, deterministic rules) |
| Megha | Research | Daily digest 14:30, launches a real Scientist OS mission |
| Veda | Inventor | Daily invention 15:30 |
| Lydia | Finance | Finance check 19:00 |
| Naina | Engineer | Tech watch 15:00, site monitor every 5 min, site report 15:20 |
| Shruti | Music teacher | Practice plan 16:00 |
| Maya | B2B outreach | Lead scout 16:30 (weekdays) |
| Kavya | Brand/media | Content idea 17:00 |

Owner-facing duties run after 14:00 IST (the owner sleeps ~05:00–14:00). Health: `curl http://127.0.0.1:8090/health` on tv-mum-01;
history in Postgres table `core.audit` (events `duty:<name>`, `alert:<name>`, `daily_report`).

### Gateway verbs added for Priya and Nitya (2026-10-22)
- `home.room` → tool `esp_status` (AV box incl. radar). **Not** `get_room_state` (shadowed by an older function).
- `home.plug.status`, `almanac.summary`, and `almanac.home_note` (Nitya may add only a **note or reminder** to the Almanac — never alarms,
  events, money or shopping).
- Allow-lists live in `DEFAULT_ALLOW` in `layla_l365.py` (the live JSON config has no `allow` override, so editing the plugin is enough).

### Nitya — what her "problem" was and the fix (2026-10-22)
Symptom: Nitya sent "bedroom fan has been on for N hours" warnings 10 times in two weeks and "can't read the fan" twice, although nobody
was home. **Cause:** the fan switch (Tuya) had been offline since 9 Oct; Tuya's status API keeps returning the *last* value it heard
("on, speed 5") for an offline device, so Nitya believed the fan was on and counted hours; "turn it off" commands were accepted by Tuya
with "success" and silently went nowhere. **Fix:** `layla…/adapters/tuya_fan.py` now asks Tuya whether the device is online first; an
offline fan returns an error ("OFFLINE, Tuya last heard from it on …") for both reads and commands. Nitya then treats the fan as
*unreadable* (not "on") and says so once every 3 days instead of daily; Almanac shows "Fan offline"; Layla no longer claims success.
New Nitya rules (all deterministic, each at most once per day): room empty ≥ 45 min but lights/fan on; room ≥ 34 °C while occupied and fan
off; fan on ≥ 8 h. Each warning is also written to the Almanac as a note titled `Home: ...`, which Priya's watcher deliberately ignores.

## WhatsApp auto-reply (`layla/python/layla_wa/`, service `layla-wa`, port 8120)

Pipeline: the phone (WaListenerService, in the Almanac APK) reads a WhatsApp / WhatsApp Business **notification**, sends it to the
server (`/wa/message`); the server decides whether and what to reply, the phone waits a human-like delay, re-checks the chat is still
unread, asks the server for a final go-ahead (`/wa/commit`, the **kill switch is checked again here**) and sends through the
notification's own inline-reply action, then reports (`/wa/ack`). Every step fails closed.

**Owner's rule (2026-10-22): the assistant answers STRANGERS only — people NOT saved in the owner's contacts. Saved contacts never get an
automatic reply.** Implemented in `engine.py`:
- `_is_stranger` requires two signals: the phone did not tag the sender as an Android contact, AND the notification title is a bare
  phone number (or WhatsApp's `~Push name`). Anything ambiguous is treated as a saved contact and skipped.
- Strangers get the `unknown` mode prompt (`SYSTEM_STRANGER`): speaks as "{owner}'s assistant" (not as the owner), 1–2 polite sentences,
  says he is away, asks who they are and what it is about, reveals nothing, no dates/prices/links/promises, no "AI/bot" wording.
  If they ask "are you a bot/AI" the deterministic honest answer is used. Business-keyword enquiries keep the `business` mode with lead capture.
- Spam filter (`_SPAM`): links, lottery/prize, loan/KYC/OTP/UPI, crypto/forex/betting, work-from-home/"earn Rs N", "your account will be
  blocked", cashback/refund, "click here" → ignored without calling the model.
- Caps: strangers max 3 replies per conversation per hour (`unknown_per_conv_per_hour`), 15 per hour in total
  (`unknown_global_per_hour`), plus the old global 60/hour. Groups: only allow-listed groups, unchanged.
- Other safety: no-tools LLM, prompt-injection scan, distress keywords escalate to Telegram, commitment/personal-data regexes replace
  risky replies with safe fallbacks, two-phase commit, every sent reply is mirrored to Telegram.

Controls: Telegram `/wa on|off|status|group add|remove|list|mute|unmute <name>`; Almanac → Phone & WhatsApp switch
(`POST /wa/power`, `GET /wa/status` with the device token). **It is OFF now.** State and audit are in `/opt/layla-wa/data/wa.db`.
Do not enable `layla_biz` (Meta/ElevenLabs Business-number path) at the same time as the on-device Business WhatsApp hook.

## Subscription portal (`layla.tryvanta.in/subscribe`, `/opt/layla-portal`, port 8160)

Tiers (365 days): **Habitat/basic ₹14,999**, **Sovereign/premium ₹29,999**, **Executive/luxury ₹79,999** (prices in `portal.env`
`PRICE_<TIER>_PAISE`). Google sign-in is invite-gated. Payments: **Cashfree** (production). Flow: `/portal/api/billing/order` creates a
Cashfree order → checkout → return URL / signed webhook → `_settle` re-reads the order from Cashfree (never trusts the caller), checks
amount and currency, marks paid idempotently and raises the tenant's tier. Plan expiry is enforced with a 3-day grace.
Data layer: Postgres `layla_tenancy`, schema `tenancy`; tenant data tables are protected by FORCE row-level security keyed on
`app.current_tenant`; connection secrets sealed with AES-256-GCM. **DDL needs the DB owner `genesis`** (via `docker exec ... psql -U genesis`), the
app role `layla_app` cannot create/alter.

### Coupons (added 2026-10-21)
Tables `tenancy.coupons`, `tenancy.coupon_redemptions` (+ nullable `payments.coupon`). Code in `billing.py` (`apply_coupon_paise`),
`db.py` (`coupon_check`, `coupon_commit`, `coupon_redeem_full`), `server.py` (`POST /portal/api/billing/coupon` = preview, `_billing_order` accepts
`coupon`). Live codes: **`LAUNCH50`** (50% off, 100 uses) and **`TRYVANTAVIP`** (100% waiver, 50 uses), both valid to 2026-11-19, all tiers.
- 50%: the discounted amount goes through Cashfree; the coupon use is committed only after the payment really settles.
- 100%: bypasses Cashfree; in ONE transaction it reserves a capped use, records the redemption (unique per code+tenant) and upgrades the tier.
  No ₹0 payment row is written because `payments.amount_paise` has a `> 0` CHECK (a never-paid tenant is exempt from expiry, i.e. free access).
- Validation is server-side only; the page preview is cosmetic. NOT yet exercised end-to-end with a real browser or a real Cashfree settlement.
- To change limits/expiry: update the `coupons` row as `layla_app` (UPDATE is granted).

Open items for launch (owner will discuss separately): one real small test payment, coupon flow in a real browser, Cashfree webhook check.
