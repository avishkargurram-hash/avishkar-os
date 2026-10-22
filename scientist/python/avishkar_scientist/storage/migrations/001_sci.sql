-- Scientist OS schema v1 (spec section 32 + engine/ledger/governance tables).
-- Idempotent: safe to re-run. Applied by storage/migrate.py inside one tx.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version     text PRIMARY KEY,
  applied_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
  id          text PRIMARY KEY,
  name        text NOT NULL,
  role        text NOT NULL DEFAULT 'researcher',  -- admin | researcher | viewer
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE SEQUENCE IF NOT EXISTS mission_seq START 1;

CREATE TABLE IF NOT EXISTS missions (
  id                    text PRIMARY KEY,                 -- SCI-000123
  user_id               text NOT NULL,
  question              text NOT NULL,
  original_prompt       text NOT NULL,
  research_depth        text NOT NULL,
  status                text NOT NULL DEFAULT 'CREATED',
  priority              int  NOT NULL DEFAULT 5,
  time_budget_s         int  NOT NULL,
  compute_budget        int  NOT NULL,                    -- max tasks
  premium_model_budget  int  NOT NULL,                    -- max Tier3+ calls
  premium_usd_budget    numeric(10,4) NOT NULL DEFAULT 0,
  evidence_threshold    real NOT NULL,
  max_tasks             int  NOT NULL,
  max_experiments       int  NOT NULL,
  termination_policy    jsonb NOT NULL DEFAULT '{}'::jsonb,
  current_phase         text NOT NULL DEFAULT 'SCOPING',
  stage                 text NOT NULL DEFAULT 'SCOPE',    -- reconciler stage within an iteration
  iteration             int  NOT NULL DEFAULT 0,
  confidence            real NOT NULL DEFAULT 0,
  rqs                   real NOT NULL DEFAULT 0,
  maturity              real NOT NULL DEFAULT 0,          -- 0..1 UI progress estimate
  evidence_strength     text NOT NULL DEFAULT 'NONE',
  stop_reason           text,
  verdict_label         text,
  paused                boolean NOT NULL DEFAULT false,
  cancel_requested      boolean NOT NULL DEFAULT false,
  source                text NOT NULL DEFAULT 'api',      -- api | layla | demo | cli
  demo                  boolean NOT NULL DEFAULT false,
  error                 text,
  created_at            timestamptz NOT NULL DEFAULT now(),
  started_at            timestamptz,
  completed_at          timestamptz,
  updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS missions_status_idx ON missions(status);

CREATE TABLE IF NOT EXISTS research_states (
  mission_id     text PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
  state          jsonb NOT NULL DEFAULT '{}'::jsonb,
  version        int NOT NULL DEFAULT 0,
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
  id                  bigserial PRIMARY KEY,
  mission_id          text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  type                text NOT NULL,                 -- e.g. lit.search, critic.run
  queue               text NOT NULL,
  priority            int  NOT NULL DEFAULT 5,
  iteration           int  NOT NULL DEFAULT 0,
  dedupe_key          text NOT NULL,
  depends_on          bigint[] NOT NULL DEFAULT '{}',
  status              text NOT NULL DEFAULT 'PENDING',
  input               jsonb NOT NULL DEFAULT '{}'::jsonb,
  output              jsonb,
  checkpoint          jsonb,
  model_requirement   text,
  tool_requirement    text,
  estimated_cost      real NOT NULL DEFAULT 0,
  estimated_duration  real NOT NULL DEFAULT 0,
  retry_policy        jsonb NOT NULL DEFAULT '{"max_attempts":3,"backoff_s":5}'::jsonb,
  attempts            int  NOT NULL DEFAULT 0,
  max_attempts        int  NOT NULL DEFAULT 3,
  available_at        timestamptz NOT NULL DEFAULT now(),
  lease_owner         text,
  lease_expires_at    timestamptz,
  last_error          text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  started_at          timestamptz,
  finished_at         timestamptz,
  UNIQUE (mission_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS tasks_ready_idx ON tasks(status, queue, available_at);
CREATE INDEX IF NOT EXISTS tasks_mission_idx ON tasks(mission_id, status);
CREATE INDEX IF NOT EXISTS tasks_lease_idx ON tasks(lease_expires_at) WHERE status = 'LEASED';

CREATE TABLE IF NOT EXISTS task_attempts (
  id           bigserial PRIMARY KEY,
  task_id      bigint NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  attempt      int NOT NULL,
  worker       text,
  status       text NOT NULL,
  error        text,
  started_at   timestamptz,
  finished_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sources (
  id              bigserial PRIMARY KEY,
  mission_id      text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  provider        text NOT NULL,                  -- arxiv | crossref | openalex | semantic_scholar | pubmed | demo
  external_id     text,
  doi             text,
  title           text NOT NULL,
  authors         jsonb NOT NULL DEFAULT '[]'::jsonb,
  year            int,
  venue           text,
  url             text,
  source_type     text NOT NULL DEFAULT 'unknown', -- journal | preprint | conference | book | dataset | unknown
  is_retracted    boolean NOT NULL DEFAULT false,
  citation_count  int,
  lineage_root    text NOT NULL,                  -- dedupe key across providers (doi / normalized title)
  referenced      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- referenced works ids (OpenAlex) for independence
  quality         real NOT NULL DEFAULT 0.5,
  relevance       real NOT NULL DEFAULT 0,
  demo_simulated  boolean NOT NULL DEFAULT false,
  analyzed        boolean NOT NULL DEFAULT false,
  query           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, lineage_root)
);

CREATE TABLE IF NOT EXISTS documents (
  id           bigserial PRIMARY KEY,
  source_id    bigint NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  kind         text NOT NULL DEFAULT 'abstract',   -- abstract | fulltext
  sha256       text NOT NULL,                      -- object store key
  text_len     int NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, kind)
);

CREATE TABLE IF NOT EXISTS hypotheses (
  id            bigserial PRIMARY KEY,
  mission_id    text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  label         text NOT NULL,          -- H1, H0, H2...
  statement     text NOT NULL,
  kind          text NOT NULL DEFAULT 'primary',   -- primary | null | alternative
  status        text NOT NULL DEFAULT 'OPEN',      -- OPEN | SUPPORTED | REFUTED | CONTESTED | UNRESOLVED
  probability   real NOT NULL DEFAULT 0.5,
  rationale     text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, label)
);

CREATE TABLE IF NOT EXISTS claims (
  id             bigserial PRIMARY KEY,
  mission_id     text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  hypothesis_id  bigint REFERENCES hypotheses(id) ON DELETE SET NULL,
  text           text NOT NULL,
  normalized     text NOT NULL,
  stance         text NOT NULL DEFAULT 'NEUTRAL',  -- toward hypothesis: SUPPORTS | REFUTES | NEUTRAL
  epistemic      text NOT NULL DEFAULT 'OBSERVATION',
  status         text NOT NULL DEFAULT 'UNVERIFIED',
  confidence     real NOT NULL DEFAULT 0,
  embedding      vector(1024),
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, normalized)
);

CREATE TABLE IF NOT EXISTS experiments (
  id                bigserial PRIMARY KEY,
  mission_id        text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  hypothesis_id     bigint REFERENCES hypotheses(id) ON DELETE SET NULL,
  kind              text NOT NULL,
  title             text NOT NULL,
  design            jsonb NOT NULL DEFAULT '{}'::jsonb,
  code              text,
  code_sha256       text,
  support_criterion text,
  status            text NOT NULL DEFAULT 'PROPOSED',
  result            jsonb,
  supports          boolean,
  reproducibility   real,
  validation_errors jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiment_runs (
  id             bigserial PRIMARY KEY,
  experiment_id  bigint NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  run_kind       text NOT NULL DEFAULT 'primary',  -- primary | replication_seed | replication_independent
  seed           int,
  status         text NOT NULL,
  exit_code      int,
  duration_s     real,
  stdout_sha256  text,
  stderr_tail    text,
  result         jsonb,
  sandbox        jsonb,
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence (
  id                 bigserial PRIMARY KEY,
  mission_id         text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  claim_id           bigint NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  source_id          bigint REFERENCES sources(id) ON DELETE CASCADE,
  experiment_run_id  bigint REFERENCES experiment_runs(id) ON DELETE CASCADE,
  stance             text NOT NULL,                 -- SUPPORTS | REFUTES (toward the claim)
  quote              text,
  quote_verified     boolean NOT NULL DEFAULT false,
  strength           real NOT NULL DEFAULT 0.5,
  epistemic          text NOT NULL DEFAULT 'OBSERVATION',
  extractor          text,                          -- model/tier or 'deterministic'
  created_at         timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT evidence_has_origin CHECK ((source_id IS NOT NULL) <> (experiment_run_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS evidence_claim_idx ON evidence(claim_id);
CREATE UNIQUE INDEX IF NOT EXISTS evidence_src_uq ON evidence(claim_id, source_id) WHERE source_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS evidence_run_uq ON evidence(claim_id, experiment_run_id) WHERE experiment_run_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS datasets (
  id           bigserial PRIMARY KEY,
  mission_id   text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  name         text NOT NULL,
  origin       text NOT NULL,          -- url / generated-by-experiment / demo
  sha256       text,
  description  text,
  synthetic    boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contradictions (
  id             bigserial PRIMARY KEY,
  mission_id     text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  claim_a        bigint NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  claim_b        bigint NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
  similarity     real NOT NULL,
  severity       text NOT NULL,
  resolution     text NOT NULL DEFAULT 'UNRESOLVED',
  explanation    text,
  resolved_by    text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, claim_a, claim_b)
);

CREATE TABLE IF NOT EXISTS critic_reports (
  id              bigserial PRIMARY KEY,
  mission_id      text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  iteration       int NOT NULL,
  role            text NOT NULL,
  score           real,                          -- 0..1 quality from this critic's viewpoint
  issues          jsonb NOT NULL DEFAULT '[]'::jsonb,
  open_questions  jsonb NOT NULL DEFAULT '[]'::jsonb,
  model           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, iteration, role)
);

CREATE TABLE IF NOT EXISTS replications (
  id                bigserial PRIMARY KEY,
  mission_id        text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  experiment_id     bigint NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
  method            text NOT NULL,   -- reseed | independent
  status            text NOT NULL,
  agreement         boolean,
  reproducibility   real,
  details           jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (experiment_id, method)
);

CREATE TABLE IF NOT EXISTS model_calls (
  id              bigserial PRIMARY KEY,
  mission_id      text,
  task_id         bigint,
  purpose         text NOT NULL,
  tier            int NOT NULL,
  provider        text,
  model           text,
  status          text NOT NULL,          -- ok | error | cache_hit | semantic_hit | denied_budget | downgraded
  input_tokens    int NOT NULL DEFAULT 0,
  output_tokens   int NOT NULL DEFAULT 0,
  cost_usd        numeric(12,6) NOT NULL DEFAULT 0,
  latency_ms      int,
  error           text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS model_calls_mission_idx ON model_calls(mission_id, tier);
CREATE INDEX IF NOT EXISTS model_calls_day_idx ON model_calls(created_at) WHERE tier >= 3;

CREATE TABLE IF NOT EXISTS tool_calls (
  id            bigserial PRIMARY KEY,
  mission_id    text,
  task_id       bigint,
  tool          text NOT NULL,
  version       text,
  status        text NOT NULL,
  input_digest  text,
  latency_ms    int,
  error         text,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
  id           bigserial PRIMARY KEY,
  mission_id   text NOT NULL,
  type         text NOT NULL,
  payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS events_mission_idx ON events(mission_id, id);

CREATE TABLE IF NOT EXISTS verdicts (
  id                 bigserial PRIMARY KEY,
  mission_id         text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  label              text NOT NULL,
  statement          text NOT NULL,
  confidence         real NOT NULL,
  evidence_strength  text NOT NULL,
  package_sha256     text NOT NULL,
  package            jsonb NOT NULL,
  narrative          text,
  council            jsonb,
  stop_reason        text,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reports (
  id           bigserial PRIMARY KEY,
  mission_id   text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  format       text NOT NULL DEFAULT 'markdown',
  sha256       text NOT NULL,
  body         text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS budgets (
  mission_id        text PRIMARY KEY REFERENCES missions(id) ON DELETE CASCADE,
  tasks_used        int NOT NULL DEFAULT 0,
  premium_calls     int NOT NULL DEFAULT 0,
  premium_usd       numeric(12,6) NOT NULL DEFAULT 0,
  local_calls       int NOT NULL DEFAULT 0,
  tool_calls        int NOT NULL DEFAULT 0,
  experiments_run   int NOT NULL DEFAULT 0,
  warned            boolean NOT NULL DEFAULT false,
  updated_at        timestamptz NOT NULL DEFAULT now()
);

-- caches ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS result_cache (
  key          text PRIMARY KEY,               -- sha256(purpose|model|prompt)
  purpose      text NOT NULL,
  response     jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS semantic_cache (
  id           bigserial PRIMARY KEY,
  purpose      text NOT NULL,
  prompt_hash  text NOT NULL,
  embedding    vector(1024) NOT NULL,
  response     jsonb NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (purpose, prompt_hash)
);

CREATE TABLE IF NOT EXISTS http_cache (
  key          text PRIMARY KEY,               -- sha256(url)
  url          text NOT NULL,
  status       int NOT NULL,
  body_sha256  text NOT NULL,
  fetched_at   timestamptz NOT NULL DEFAULT now()
);

-- governance --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS approvals (
  id           bigserial PRIMARY KEY,
  mission_id   text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  kind         text NOT NULL,                  -- physical_experiment | budget_extension | ...
  request      jsonb NOT NULL,
  status       text NOT NULL DEFAULT 'PENDING',  -- PENDING | APPROVED | REJECTED
  decided_by   text,
  decided_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_log (
  id           bigserial PRIMARY KEY,
  actor        text NOT NULL,
  action       text NOT NULL,
  target       text,
  detail       jsonb,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provenance (
  id           bigserial PRIMARY KEY,
  mission_id   text NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
  from_kind    text NOT NULL,     -- source | document | claim | evidence | experiment_run | hypothesis | verdict
  from_id      text NOT NULL,
  to_kind      text NOT NULL,
  to_id        text NOT NULL,
  relation     text NOT NULL,     -- extracted_from | supports | refutes | produced | cites | decided_by
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, from_kind, from_id, to_kind, to_id, relation)
);

CREATE TABLE IF NOT EXISTS notifications (
  id            bigserial PRIMARY KEY,
  mission_id    text,
  kind          text NOT NULL,      -- milestone | verdict | report | failure
  title         text NOT NULL,
  body          text NOT NULL,
  status        text NOT NULL DEFAULT 'PENDING',   -- PENDING | SENT | FAILED | SKIPPED
  attempts      int NOT NULL DEFAULT 0,
  last_error    text,
  not_before    timestamptz NOT NULL DEFAULT now(),
  sent_at       timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (mission_id, kind, title)
);
