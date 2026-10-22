"""Router: one quick retry on the FIRST candidate for transient capacity errors (429 / overloaded /
unavailable) before falling to slower providers. Measured 2026-10-12: Cerebras 429s came back in ~30 ms
on ~11% of turns and the fallback chain (Groq 429 -> OpenRouter free -> Gemini) turned 2 s replies into 4-10 s.
Usage: python patch_router_retry.py [path]. Idempotent, anchored."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/avishkar/router/python/avishkar_router/router.py"
s = open(p, encoding="utf-8").read()
if "_TRANSIENT_RETRY" in s:
    print("already patched"); sys.exit(0)

old_imp = "from .errors import DuplicateModelError, NoAvailableProviderError, NoMatchingModelError, ProviderError\n"
assert s.count(old_imp) == 1
s = s.replace(old_imp, old_imp +
              "from .errors import ProviderOverloadedError, ProviderUnavailableError, RateLimitError\n\n"
              "# one fast retry of the first-choice model for transient capacity blips (seconds saved per hit)\n"
              "_TRANSIENT_RETRY = (RateLimitError, ProviderOverloadedError, ProviderUnavailableError)\n"
              "_RETRY_DELAY_S = 0.35\n", 1)

old = """            start = time.monotonic()
            try:
                result = provider.complete(request, model_id=model_id)
            except ProviderError as exc:
"""
assert s.count(old) == 1
new = """            start = time.monotonic()
            try:
                try:
                    result = provider.complete(request, model_id=model_id)
                except _TRANSIENT_RETRY as first_exc:
                    if model_id != candidates[0] or (time.monotonic() - start) > 1.5:
                        raise
                    try:
                        self._logger.warning("Transient provider error, retrying once", model=model_id,
                                             provider=provider.name, error_type=type(first_exc).__name__)
                    except Exception:
                        pass
                    time.sleep(_RETRY_DELAY_S)
                    result = provider.complete(request, model_id=model_id)
            except ProviderError as exc:
"""
s = s.replace(old, new, 1)
# candidates[0] needs a real sequence (select_candidates could return any iterable)
old_c = "        candidates = self._policy.select_candidates(request)\n"
assert s.count(old_c) == 1
s = s.replace(old_c, "        candidates = list(self._policy.select_candidates(request))\n", 1)
open(p, "w", encoding="utf-8").write(s)
print("router retry patched")
