# layla_comms

Isolated communications agent (Phase 0 architecture + Phase 1 Gmail triage).
Standalone: imports nothing from `layla_service` / `avishkar_layla`.

## Safety design
- The model has **no tools**. Text in, strict JSON out; malformed output = `needs_human`.
- All side effects go through `effects.Effects` (kill switch -> shadow/live flag -> audit -> act).
- No send/reply/forward exists anywhere (Effects, GmailPort, GmailClient). Drafts only.
- Archive needs LLM category + confidence >= 0.85 + a header signal (List-Unsubscribe, bulk, noreply) + non-VIP.
- Injection hits (regex or model-flagged) disable draft and archive for that message.
- Drafts with money, dates/times, promises, legal terms, links, other addresses or phone numbers are withheld; owner is pinged.
- Everything starts in **shadow mode**; enable per action: `live label on`, `live archive on`, `live draft on`.
- Hash-chained audit log (`audit`, `status` verifies the chain).

## Layout
types, firewall, policy, store, effects, llm, triage, digest, gmail, notify, cli, oauth_setup, tests/

## Run
    python -m layla_comms.oauth_setup <client_id> <client_secret>   # once, on your PC
    python -m layla_comms.cli status
    python -m layla_comms.cli poll          # cron/systemd timer, e.g. every 5 min
    python -m layla_comms.cli digest        # cron, e.g. 08:00 IST
    python -m layla_comms.cli kill on|off
    python -m layla_comms.cli contact boss@x.com vip

Tests: `python -m pytest layla_comms/tests -q` from `Avishkar-OS/layla/python`.
