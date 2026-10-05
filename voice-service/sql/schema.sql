-- Voice Service schema, applied by voice_service.db.apply_schema() at
-- startup. Idempotent: safe to run on every boot (same pattern as
-- repository-service/sql/schema.sql, decision 031).
--
-- One row per interview turn — question and answer together (decision
-- 010). Inserted as 'asked' when the question is sent, updated to
-- 'answered' when the answer arrives, so an interrupted interview still
-- records what was asked (decision 008).
--
-- interview_id has NO foreign key to interviews: that table belongs to
-- Core API, and no service depends on another's tables (decisions 021,
-- 040). Voice Service only learns an interview_id from a successful
-- token consume, which is the integrity guarantee.

CREATE TABLE IF NOT EXISTS turns (
    id                  BIGSERIAL PRIMARY KEY,
    interview_id        BIGINT NOT NULL,
    seq                 INT NOT NULL,             -- 1-based within the interview
    question_text       TEXT NOT NULL,
    -- code_chunks ids the question was generated from. Chunk ids are only
    -- unique per repository (decision 031); the interview pins the repo.
    retrieved_chunk_ids BIGINT[] NOT NULL,
    answer_text         TEXT NULL,
    status              TEXT NOT NULL DEFAULT 'asked'
                        CHECK (status IN ('asked', 'answered')),
    timings             JSONB NOT NULL DEFAULT '{}'::jsonb,  -- per-stage ms (decision 034)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    answered_at         TIMESTAMPTZ NULL,
    CONSTRAINT uq_turns_interview_seq UNIQUE (interview_id, seq)
);

-- uq_turns_interview_seq's index already serves WHERE interview_id = ?
-- (leading column), so no separate index on interview_id is needed.
