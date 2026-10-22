-- Layla 365 core schema. Run as the Postgres superuser (l365_admin) in database layla365.
-- Agents get row-level-security'd access: each agent role only sees/writes rows where agent = its own name.

CREATE SCHEMA IF NOT EXISTS core AUTHORIZATION l365_core;

CREATE TABLE IF NOT EXISTS core.agent_state (
  agent      text PRIMARY KEY,
  enabled    boolean NOT NULL DEFAULT true,
  mode       text NOT NULL DEFAULT 'shadow' CHECK (mode IN ('shadow','live')),
  note       text,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.heartbeat (
  component text PRIMARY KEY,
  ts        timestamptz NOT NULL DEFAULT now(),
  info      jsonb
);

CREATE TABLE IF NOT EXISTS core.usage (
  day        date   NOT NULL,
  agent      text   NOT NULL,
  tier       text   NOT NULL,            -- 'local' | 'heavy' | 'embed'
  calls      int    NOT NULL DEFAULT 0,
  tokens_in  bigint NOT NULL DEFAULT 0,
  tokens_out bigint NOT NULL DEFAULT 0,
  PRIMARY KEY (day, agent, tier)
);

CREATE TABLE IF NOT EXISTS core.approvals (
  id         bigserial PRIMARY KEY,
  ts         timestamptz NOT NULL DEFAULT now(),
  agent      text NOT NULL,
  kind       text NOT NULL,
  summary    text,
  params     jsonb,
  status     text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','expired')),
  decided_at timestamptz,
  decided_by text,
  expires_at timestamptz NOT NULL DEFAULT now() + interval '24 hours'
);

CREATE TABLE IF NOT EXISTS core.actions (
  id          bigserial PRIMARY KEY,
  ts          timestamptz NOT NULL DEFAULT now(),
  agent       text NOT NULL,
  kind        text NOT NULL,
  tier        text NOT NULL,
  status      text NOT NULL,   -- shadow|executed|failed|no_executor|pending_approval|approved|rejected|denied|blocked
  reason      text,
  params      jsonb,
  result      jsonb,
  approval_id bigint REFERENCES core.approvals(id)
);
CREATE INDEX IF NOT EXISTS actions_agent_ts ON core.actions (agent, ts);

CREATE TABLE IF NOT EXISTS core.audit (
  id     bigserial PRIMARY KEY,
  ts     timestamptz NOT NULL DEFAULT now(),
  agent  text NOT NULL,
  event  text NOT NULL,
  detail jsonb
);
CREATE INDEX IF NOT EXISTS audit_agent_ts ON core.audit (agent, ts);

ALTER TABLE core.agent_state OWNER TO l365_core;
ALTER TABLE core.heartbeat   OWNER TO l365_core;
ALTER TABLE core.usage       OWNER TO l365_core;
ALTER TABLE core.approvals   OWNER TO l365_core;
ALTER TABLE core.actions     OWNER TO l365_core;
ALTER TABLE core.audit       OWNER TO l365_core;
ALTER SEQUENCE core.approvals_id_seq OWNER TO l365_core;
ALTER SEQUENCE core.actions_id_seq   OWNER TO l365_core;
ALTER SEQUENCE core.audit_id_seq     OWNER TO l365_core;

-- Row level security: an agent sees and writes ONLY its own rows (owner l365_core bypasses).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['usage','approvals','actions','audit'] LOOP
    EXECUTE format('ALTER TABLE core.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS own_rows ON core.%I', t);
    EXECUTE format('CREATE POLICY own_rows ON core.%I USING (agent = substr(current_user, 6)) WITH CHECK (agent = substr(current_user, 6))', t);
  END LOOP;
END $$;

-- Privileges for the nine agent roles
GRANT USAGE ON SCHEMA core TO l365_naina, l365_megha, l365_veda, l365_priya, l365_nitya, l365_shruti, l365_lydia, l365_maya, l365_kavya;
GRANT SELECT ON core.agent_state, core.heartbeat
  TO l365_naina, l365_megha, l365_veda, l365_priya, l365_nitya, l365_shruti, l365_lydia, l365_maya, l365_kavya;
GRANT SELECT, INSERT, UPDATE ON core.usage, core.actions
  TO l365_naina, l365_megha, l365_veda, l365_priya, l365_nitya, l365_shruti, l365_lydia, l365_maya, l365_kavya;
GRANT SELECT, INSERT ON core.approvals, core.audit            -- append-only for agents
  TO l365_naina, l365_megha, l365_veda, l365_priya, l365_nitya, l365_shruti, l365_lydia, l365_maya, l365_kavya;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA core
  TO l365_naina, l365_megha, l365_veda, l365_priya, l365_nitya, l365_shruti, l365_lydia, l365_maya, l365_kavya;
