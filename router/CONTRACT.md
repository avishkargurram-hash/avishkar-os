# AI Router Framework — Language-Agnostic Contract

The source of truth for what "AI Router" means, independent of language —
mirrors [`core/CONTRACT.md`](../core/CONTRACT.md)'s approach (ADR-0008).
Python ships first ([`python/avishkar_router/`](./python/avishkar_router/));
conformance is judged against this document and [`schemas/`](./schemas/),
not against the Python source.

---

## 1. Core types

```
ModelSpec {
  model_id: string
  provider: string                 # the ModelProvider.name that serves it
  capabilities: string[]           # e.g. ["chat","tools","vision","thinking"]
  input_cost_per_mtok: number      # USD per 1,000,000 input tokens
  output_cost_per_mtok: number     # USD per 1,000,000 output tokens
  max_context_tokens: int
  max_output_tokens: int
}

Message { role: "user" | "assistant" | "system", content: string }

CompletionRequest {
  messages: Message[]
  model: string | null             # explicit override -- see SS3
  capabilities: string[] = []      # required capabilities, for auto-selection
  task_type: string | null = null  # optional policy-matching hint
  max_tokens: int = 1024
  metadata: map<string, any> = {}  # metadata.caller attributes cost -- see SS4
}

ProviderResponse {                 # returned by ModelProvider.complete()
  content: string
  input_tokens: int
  output_tokens: int
  stop_reason: string | null
  raw: any | null                  # provider-native response, for advanced use
  request_id: string | null        # provider's own request/message id, when it has one (Priority 17.5)
}

CompletionResponse {               # returned by Router.route()
  content: string
  model_used: string
  provider_used: string
  input_tokens: int
  output_tokens: int
  cost_usd: number
  latency_ms: number
  stop_reason: string | null
  request_id: string | null        # Priority 17.5, ADR-0025 -- see ProviderResponse.request_id
}
```

Sampling parameters (`temperature`, `top_p`, `top_k`) are deliberately
**not** part of `CompletionRequest` v1 — see [README.md](./README.md)
Limitations. `CompletionRequest` carries only `text`-typed message
content in v1; multi-modal content blocks are a documented Future Roadmap
item, not silently unsupported-but-implied.

---

## 2. ModelProvider — the adapter interface

Every provider adapter (Anthropic, a future OpenAI/Google adapter, the
reference `MockProvider`) implements this. A provider never talks to the
Router directly — it only ever receives a `CompletionRequest` and an
explicit `model_id`, and returns a `ProviderResponse` or raises a
`ProviderError` subtype.

```
ModelProvider.name -> string                    # stable identifier, e.g. "anthropic"
ModelProvider.list_models() -> ModelSpec[]
ModelProvider.complete(request: CompletionRequest, model_id: string) -> ProviderResponse
  throws AuthenticationError | RateLimitError | InvalidRequestError
       | ProviderOverloadedError | ProviderTimeoutError | ProviderUnavailableError
```

**Error normalization is mandatory.** A provider adapter must translate
its underlying SDK/HTTP errors into this shared taxonomy
(`errors.py` / the equivalent in another language) before they leave
`complete()`. The Router's fallback logic depends on catching one shared
hierarchy, not on knowing every provider's native exceptions — see
[README.md](./README.md) Anti-Patterns.

---

## 3. RoutingPolicy — candidate selection

```
RoutingRule {
  capabilities: string[] = []      # request.capabilities must be a superset
  task_type: string | null = null  # if set, must equal request.task_type
  models: string[]                 # ordered candidates, tried in order
}

RoutingPolicy {
  default_model: string
  rules: RoutingRule[]             # first matching rule wins
}

RoutingPolicy.select_candidates(request: CompletionRequest) -> string[]
  # 1. request.model set explicitly -> [request.model] ONLY -- no
  #    automatic substitution away from an explicit caller choice.
  # 2. else: first rule whose task_type/capabilities match -> rule.models
  # 3. else: [default_model]
```

Explicit `request.model` deliberately skips fallback — see README.md
Best Practices for why (silently substituting away from an explicit
choice is a footgun a caller has no way to opt out of).

---

## 4. Router — orchestration

```
Router(providers: ModelProvider[], policy: RoutingPolicy) -> Router

Router.route(request: CompletionRequest) -> CompletionResponse
  throws NoMatchingModelError    # a candidate model_id isn't registered
                                  # by any provider passed to the Router
  throws NoAvailableProviderError # every candidate for this request failed
  # Tries policy.select_candidates(request) in order. For each: times the
  # call, catches ProviderError subtypes and moves to the next candidate
  # (logging + publishing "router.fallback" via EventBus if available),
  # computes cost_usd from the winning model's ModelSpec pricing, records
  # it against request.metadata["caller"] via CostTracker, and returns.

Router.list_models() -> ModelSpec[]   # every model across every registered provider

CostTracker.total_cost_usd(caller: string | null = null) -> number
  # caller=null -> cumulative cost across all callers
```

**Duplicate `model_id` across two providers is a construction-time
error** — the Router refuses to build an ambiguous registry rather than
silently picking one.

---

## Cross-cutting rules

- **Depends on Core Engine only** (ARCHITECTURE.md §5): `Logger` for
  structured routing/fallback logs, `EventBus` for `router.fallback` /
  `router.request.completed` events, optionally `Config` for loading a
  `RoutingPolicy`. No dependency on any specific provider SDK at the
  Router/policy layer — only a provider *adapter* may depend on its
  vendor's SDK.
- **No component depends on another component's concrete class** — a
  `Router` depends on the `ModelProvider` interface, never on
  `AnthropicProvider` by name.
