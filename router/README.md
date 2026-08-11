# AI Router Framework

## Vision
Every Chief Domain Agent, workflow, and prompt in Avishkar OS needs to
call a language model — but "which model, from which provider, at what
cost, with what fallback if it's down" should never be decided ad hoc
inside each caller. AI Router Framework is the single place that
decision lives: a provider-agnostic routing layer that picks a model by
policy (capability match, task-type hint, or explicit override), falls
back through alternatives on failure, and tracks what every call cost —
so a Chief Domain Agent's code never imports a vendor SDK directly, and
switching or adding a provider never means touching agent code.

Built as Phase 2 (ROADMAP.md, per ADR-0009) precisely because Agent
Framework — Phase 3 — cannot be genuinely "done" without a router every
agent can depend on, the same way every framework depends on Core Engine.

## Architecture

```
router/
├── CONTRACT.md          the language-agnostic interface spec (source of truth)
├── schemas/               JSON Schemas for the shared data shapes
├── python/                Python reference implementation
│   └── avishkar_router/
│       ├── types.py         Message, ModelSpec, CompletionRequest/Response
│       ├── provider.py      ModelProvider (the adapter interface)
│       ├── policy.py        RoutingPolicy, RoutingRule
│       ├── router.py        Router, CostTracker
│       ├── errors.py        ProviderError / RouterError hierarchies
│       └── providers/
│           ├── mock.py              MockProvider -- no network, for tests/examples
│           └── anthropic_provider.py AnthropicProvider -- real Anthropic API calls
└── examples/
    └── quickstart.py     policy routing, fallback, cost tracking, all network-free
```

Request flow: a caller builds a `CompletionRequest` → `Router.route()`
asks the `RoutingPolicy` for an ordered candidate list → tries each
candidate's registered `ModelProvider.complete()` in order, catching
`ProviderError` and moving to the next candidate on failure → on success,
computes `cost_usd` from the winning model's `ModelSpec` pricing, records
it against `request.metadata["caller"]` in `CostTracker`, and returns a
`CompletionResponse`. Every step logs through Core Engine's `Logger` and
optionally publishes `router.fallback` / `router.request.completed`
events through Core Engine's `EventBus` — see
[`examples/quickstart.py`](./examples/quickstart.py) for all of this
running end to end.

## Folder Structure
See the tree above. A second provider adapter (OpenAI, Google, a second
Anthropic-compatible endpoint) is a new file under `providers/` — see
Extension Model.

## Naming Standards
Follows [STANDARDS.md](../STANDARDS.md) §3. Provider adapter files are
named `<vendor>_provider.py`; the class is `<Vendor>Provider`.

## Interfaces

**Router** — `Router(providers, policy, *, event_bus=None, cost_tracker=None)`;
`.route(request: CompletionRequest) -> CompletionResponse`, `.list_models()`,
`.cost_tracker -> CostTracker`.

**RoutingPolicy** — `RoutingPolicy(default_model, rules=())`;
`.select_candidates(request) -> tuple[str, ...]`;
`RoutingPolicy.from_config(config: avishkar_core.Config)`.

**ModelProvider** (ABC, implement to add a vendor) — `.name`,
`.list_models() -> tuple[ModelSpec, ...]`,
`.complete(request, *, model_id) -> ProviderResponse`.

**CostTracker** — `.record(cost_usd, caller)`,
`.total_cost_usd(caller=None) -> float`.

Full signatures, error conditions, and semantics: [`CONTRACT.md`](./CONTRACT.md).

## Extension Model
Add a new provider by subclassing `ModelProvider`, publishing its
`ModelSpec`s from `list_models()`, and normalizing its SDK's exceptions
into the shared `ProviderError` hierarchy (`errors.py`) inside
`complete()` — see `providers/anthropic_provider.py` as the reference. No
change to `Router` or `RoutingPolicy` is needed; register the new
provider instance alongside existing ones when constructing a `Router`.
A new routing strategy (e.g. latency-weighted, not just ordered
fallback) is a new `RoutingPolicy`-shaped class satisfying
`select_candidates(request) -> tuple[str, ...]` — `Router` only depends
on that method existing, not on `RoutingPolicy` being the only
implementation.

## Examples

```bash
python router/examples/quickstart.py
```

Minimal routing with the network-free `MockProvider`:

```python
from avishkar_router import CompletionRequest, Message, MockProvider, RoutingPolicy, Router

router = Router([MockProvider()], RoutingPolicy(default_model="mock-fast"))
response = router.route(CompletionRequest(messages=(Message(role="user", content="hi"),)))
print(response.content, response.cost_usd)
```

Real Anthropic calls (requires `pip install anthropic` and
`ANTHROPIC_API_KEY`, or an `ant auth login` profile):

```python
from avishkar_router import CompletionRequest, Message, RoutingPolicy, Router
from avishkar_router.providers.anthropic_provider import AnthropicProvider

router = Router([AnthropicProvider()], RoutingPolicy(default_model="claude-opus-5"))
response = router.route(CompletionRequest(messages=(Message(role="user", content="hi"),)))
```

## Best Practices
- Attribute cost by setting `request.metadata["caller"]` to the calling
  framework/agent's name — `CostTracker.total_cost_usd(caller)` is only
  useful if every caller does this consistently.
- Use `task_type` / `capabilities` for policy-driven selection when the
  caller doesn't care which model handles it (let the platform optimize
  cost/latency); use an explicit `model` only when the caller has a real
  reason to require one specific model — and remember that skips fallback
  entirely (CONTRACT.md §3).
- Register every provider a policy's rules can reference *before*
  constructing the `Router` — a policy naming an unregistered model fails
  fast with `NoMatchingModelError` at route time, not silently.

## Anti-Patterns
- Catching a provider's vendor-specific exception type outside the
  provider adapter — e.g. `except anthropic.RateLimitError` in calling
  code. That defeats the entire point of the normalized `ProviderError`
  hierarchy; catch `RateLimitError` from `avishkar_router.errors` instead,
  which works regardless of which provider actually served the request.
- Constructing a vendor SDK client directly inside a Chief Domain Agent
  or workflow instead of going through a `Router` — reintroduces the
  per-caller vendor coupling this framework exists to remove.
- Relying on `request.model` for cost-saving fallback — an explicit model
  is a hard requirement, not a preference; use a `RoutingRule` if
  fallback is actually wanted.

## Future Roadmap
- Sampling-parameter passthrough (`temperature`/`top_p`/`top_k`) —
  deliberately out of v1 (see Limitations); revisit once a concrete
  caller needs it and per-model support is less of a moving target.
- Multi-modal `CompletionRequest` content (images, documents) — v1 is
  text-only.
- A second provider adapter (OpenAI or Google) once Agent Framework
  (Phase 3) or a product surfaces a real multi-vendor need — YAGNI until
  then.
- Budget/quota enforcement (`BudgetExceededError`) on top of the
  observational `CostTracker` that exists today.
- A second language implementation of `CONTRACT.md`, on the same
  cadence as Core Engine's (see `core/README.md` Future Roadmap).

---

## Limitations

Stated honestly, per STANDARDS.md's rule that a Limitations section must
be true, not aspirational:

- **No sampling-parameter control.** `CompletionRequest` has no
  `temperature`/`top_p`/`top_k`. Current-generation Claude models reject
  non-default sampling parameters outright, and support varies
  significantly across providers and model generations — encoding that
  into a stable v1 contract would either be wrong for some models or
  force per-provider special cases into the shared type. Steer model
  behavior via prompting instead; this is deliberate, not an oversight.
- **Text-only messages.** `Message.content` is a plain string. No image,
  document, or tool-use content blocks yet — every current caller
  (Core Engine's quickstart-level examples) only needs text.
- **No budget enforcement.** `CostTracker` observes and reports; it does
  not reject a request for exceeding a budget. Add that when a caller
  needs it, not preemptively.
- **`AnthropicProvider` is the only real network-calling adapter.** It
  was built and tested against the official `anthropic` Python SDK
  (version-pinned via the `avishkar-router[anthropic]` extra), with its
  error-normalization logic unit-tested against the real SDK's exception
  classes constructed directly (no network access was available in the
  environment this framework was built in, so a live end-to-end call
  against api.anthropic.com has not been exercised here — only the
  request/response/error shapes, which are stable and documented). A
  real, opt-in, env-gated live test exercising this exact provider
  through Layla's full pipeline now exists (Avishkar OS Priority 17.5,
  ADR-0025 — `layla/python/tests/test_live_anthropic_integration.py`,
  `docs/live-integration-guide.md`); it was also not run against a real
  key during that work (no credentials available then either) — stated
  the same way there, not glossed over here.
- **No streaming.** `ModelProvider.complete()` returns one complete
  response. A long-running agent that wants token-by-token output needs
  a future `stream()` method on the interface — not added speculatively.
