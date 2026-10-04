# Voice Service

Runs RepoViva's live interview session over a WebSocket. **Not implemented yet.**

## Planned responsibilities

- Accept the client's WebSocket and read the session token from its first `session.start` message, never from the URL (decision 035).
- Consume that token once via Core API's `/internal/v1/session-tokens/consume`.
- For each turn: STT → retrieval from Repository Service → generate the next question with the LLM (decision 034) → stream TTS audio back.
- Persist each turn as it completes, and discard raw audio (decision 009).
- Report `interview.completed` or `interview.interrupted` to Core API (decision 036).

STT, TTS and LLM providers are not chosen yet. The message protocol is sketched in [docs/architecture.md](../docs/architecture.md#websocket--served-by-voice-service).
