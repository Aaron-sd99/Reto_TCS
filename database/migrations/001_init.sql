CREATE TABLE IF NOT EXISTS accounts (
    account_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL,
    currency CHAR(3) NOT NULL,
    available_balance NUMERIC(18, 2) NOT NULL CHECK (available_balance >= 0),
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transfers (
    id UUID PRIMARY KEY,
    idempotency_key VARCHAR(128) NOT NULL UNIQUE,
    source_account VARCHAR(32) NOT NULL,
    destination_account VARCHAR(32) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    customer_id VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    core_reference VARCHAR(64),
    rejection_reason TEXT,
    correlation_id VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_transfers_status ON transfers(status);
CREATE INDEX IF NOT EXISTS idx_transfers_correlation_id ON transfers(correlation_id);

CREATE TABLE IF NOT EXISTS ledger_entries (
    id BIGSERIAL PRIMARY KEY,
    transfer_id UUID NOT NULL REFERENCES transfers(id),
    account_id VARCHAR(32) NOT NULL,
    entry_type VARCHAR(24) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ledger_transfer_id ON ledger_entries(transfer_id);
CREATE INDEX IF NOT EXISTS idx_ledger_account_id ON ledger_entries(account_id);

CREATE TABLE IF NOT EXISTS outbox_events (
    id UUID PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending ON outbox_events(status, created_at);

CREATE TABLE IF NOT EXISTS processed_messages (
    consumer VARCHAR(64) NOT NULL,
    message_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer, message_id)
);

CREATE TABLE IF NOT EXISTS ai_recommendations (
    id UUID PRIMARY KEY,
    transfer_id UUID NOT NULL REFERENCES transfers(id),
    customer_id VARCHAR(32) NOT NULL,
    recommendation_type VARCHAR(64) NOT NULL,
    message TEXT NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bancs_accounts (
    account_id VARCHAR(32) PRIMARY KEY,
    currency CHAR(3) NOT NULL,
    available_balance NUMERIC(18, 2) NOT NULL CHECK (available_balance >= 0),
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS bancs_postings (
    core_reference VARCHAR(64) PRIMARY KEY,
    source_account VARCHAR(32) NOT NULL,
    destination_account VARCHAR(32) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(24) NOT NULL,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO accounts (account_id, customer_id, currency, available_balance, status)
VALUES
    ('ACC-1001', 'CUS-001', 'USD', 1000.00, 'ACTIVE'),
    ('ACC-1002', 'CUS-001', 'USD', 100.00, 'ACTIVE'),
    ('ACC-2001', 'CUS-002', 'USD', 500.00, 'ACTIVE'),
    ('ACC-3001', 'CUS-003', 'USD', 10000.00, 'ACTIVE'),
    ('ACC-3002', 'CUS-003', 'USD', 5.00, 'ACTIVE'),
    ('ACC-4001', 'CUS-004', 'EUR', 750.00, 'ACTIVE'),
    ('ACC-9001', 'CUS-009', 'USD', 250.00, 'INACTIVE')
ON CONFLICT (account_id) DO NOTHING;

INSERT INTO bancs_accounts (account_id, currency, available_balance, status)
VALUES
    ('ACC-1001', 'USD', 1000.00, 'ACTIVE'),
    ('ACC-1002', 'USD', 100.00, 'ACTIVE'),
    ('ACC-2001', 'USD', 500.00, 'ACTIVE'),
    ('ACC-3001', 'USD', 10000.00, 'ACTIVE'),
    ('ACC-3002', 'USD', 5.00, 'ACTIVE'),
    ('ACC-4001', 'EUR', 750.00, 'ACTIVE'),
    ('ACC-9001', 'USD', 250.00, 'INACTIVE')
ON CONFLICT (account_id) DO NOTHING;
