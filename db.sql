CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.credentials (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  username TEXT NOT NULL,
  password TEXT NOT NULL,    -- MVP: plain; upgrade to KMS/Vault later
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth.tokens (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  kind TEXT NOT NULL,        -- 'bearer' | 'cookie'
  token TEXT,                -- bearer or opaque string
  cookies JSONB,             -- for cookie sessions
  expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth.telemetry (
  id BIGSERIAL PRIMARY KEY,
  site_id TEXT NOT NULL,
  endpoint TEXT NOT NULL,
  status INT NOT NULL,
  latency_ms DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);
