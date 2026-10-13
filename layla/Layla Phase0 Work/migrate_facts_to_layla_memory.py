"""
One-time migration: re-write every existing 'semantic' fact (written by the
old remember_fact, as a bare JSON value) through LaylaMemoryPolicy so it
gets a real MemoryRecord envelope (confidence/provenance/importance/
stored_at) -- required before remember_fact/recall_fact switch to reading
through _layla_memory, since LaylaMemoryPolicy.recall() does
MemoryRecord(**raw) and would fail on the old bare-value shape.

Idempotent: re-running after the switchover just re-wraps an
already-wrapped record with a fresh 'migrated' provenance -- harmless, but
only meant to run once, before the code switch.
"""
import sys
sys.path.insert(0, "/opt/layla")
import layla_service as L

migrated = []
for key in L._memory.list_keys("semantic"):
    raw = L._memory.recall("semantic", key)
    if isinstance(raw, dict) and set(raw.keys()) >= {"value", "confidence", "provenance", "importance", "stored_at"}:
        print(f"SKIP (already migrated): semantic:{key!r}")
        continue
    L._layla_memory.remember("semantic", key, raw, confidence=1.0, provenance="migrated", importance="normal")
    migrated.append(key)
    print(f"MIGRATED: semantic:{key!r} -> {raw!r}")

print(f"\nDone. Migrated {len(migrated)} key(s): {migrated}")
