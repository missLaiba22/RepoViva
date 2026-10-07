-- Evaluation Service schema, applied by evaluation_service.db.apply_schema()
-- at startup. Idempotent: safe to run on every boot (same pattern as
-- voice-service/sql/schema.sql, decision 031).
--
-- One row per interview's report (decisions 049, 050). The row is written
-- as 'generating' before any work starts, so the table doubles as a
-- durable job list: on boot, every report still 'generating' is resumed.
--
-- interview_id has NO foreign key to interviews: that table belongs to
-- Core API, and no service depends on another's tables (decisions 021,
-- 040). Core API is the only caller of the trigger, so ids come from it.

CREATE TABLE IF NOT EXISTS reports (
    id               BIGSERIAL PRIMARY KEY,
    interview_id     BIGINT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'generating'
                     CHECK (status IN ('generating', 'ready', 'failed')),
    -- Needed to fetch chunks, and to regenerate without a new trigger.
    repository_id    BIGINT NOT NULL,
    -- True when the interview ended 'interrupted' (decision 008).
    partial          BOOLEAN NOT NULL,
    -- Which model and prompt produced the scores, so reports from
    -- different prompts are never compared by mistake (decision 050).
    model            TEXT NULL,
    prompt_version   TEXT NULL,
    summary          JSONB NULL,   -- averages, strengths, improvements, files
    turn_evaluations JSONB NULL,   -- one entry per turn, incl. not_answered / not_graded
    error_message    TEXT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ NULL,
    CONSTRAINT uq_reports_interview UNIQUE (interview_id)
);

-- Startup resume scans for unfinished reports. Partial, so it stays tiny:
-- almost every row is 'ready'.
CREATE INDEX IF NOT EXISTS ix_reports_generating
    ON reports (created_at) WHERE status = 'generating';
