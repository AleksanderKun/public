CREATE TABLE IF NOT EXISTS market_observations (
    event_id TEXT PRIMARY KEY,
    timestamp_utc TIMESTAMPTZ NOT NULL,
    source_timestamp_utc TIMESTAMPTZ,
    source TEXT NOT NULL,
    exchange TEXT NOT NULL,
    market_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    metric TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS market_observations_metric_time_idx ON market_observations (metric, timestamp_utc DESC);
SELECT create_hypertable('market_observations', by_range('timestamp_utc'), if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS market_regimes (
    timestamp_utc TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    primary_regime TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    evidence JSONB NOT NULL,
    counter_evidence JSONB NOT NULL,
    is_model_estimate BOOLEAN NOT NULL DEFAULT TRUE
);