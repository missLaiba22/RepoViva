# Engineering Decisions

## 001 — Support both public and private GitHub repositories

**Decision:**
RepoViva supports connecting both public and private GitHub repositories.

**Why:**
Developers often want to practice on real work projects, which are usually private. Restricting to public repos would exclude the highest-value use case.

**Tradeoff:**
Requires GitHub OAuth flow, token storage, and application-level token encryption. This is the single biggest scope expander in the security surface — a leaked token gives an attacker access to a user's private GitHub.

**Revisit when:**
Token management becomes a significant operational burden, or a security incident indicates the risk outweighs the feature.

---

## 002 — Multiple interviews per repository

**Decision:**
Once a repository is connected, users can run multiple interviews against it.

**Why:**
Repository analysis is expensive and is already persisted for reuse. Allowing multiple interviews is essentially free once the analysis exists.

**Tradeoff:**
Repositories become long-lived entities tied to a user, requiring per-user listing, ownership checks, and eventual cleanup logic.

**Revisit when:**
Storage cost from stale repositories becomes an operational issue.

---

## 003 — Voice-only interview modality

**Decision:**
The interview happens exclusively via voice-to-voice interaction. No text-based interview modality in MVP.

**Why:**
Voice-to-voice is the product's core differentiator. Building a text alternative would split effort and dilute the identity of the product.

**Tradeoff:**
Users with broken mics or in noisy environments cannot use the product. Debugging the interview logic during development is harder without a text path.

**Revisit when:**
User feedback consistently indicates the need for text fallback, or accessibility requirements demand it.

---

## 004 — GitHub OAuth as the only authentication method

**Decision:**
Users authenticate exclusively through GitHub OAuth. No email/password login.

**Why:**
Every user of RepoViva has a GitHub account by definition. GitHub OAuth also grants the access needed for private repos, so it doubles as authorization for that.

**Tradeoff:**
Users who prefer not to log in via GitHub cannot use the product. Dependency on GitHub's OAuth availability.

**Revisit when:**
Non-GitHub source providers are ever supported.

---

## 005 — Encryption: application-level for OAuth tokens, disk-level for repo content and reports

**Decision:**
GitHub OAuth tokens (access + refresh) are encrypted at the application layer before being written to the database. Repository code, embeddings, and reports rely on database/disk-level encryption only.

**Why:**
Tokens are the highest-risk data — they grant access to the user's GitHub. Application-level encryption of repo contents would break vector retrieval (embeddings must be plaintext for similarity search) and create a heavy key-management burden without meaningfully raising the security bar.

**Tradeoff:**
An attacker who compromises the application server can read repo contents in memory. Fully application-level encryption would raise the bar further, at high implementation cost.

**Revisit when:**
The product moves toward multi-tenant / enterprise use, or the threat model changes to include stronger insider-attack protection.

---

## 006 — Interview turn latency target: 4–5s p95

**Decision:**
The MVP target for interview turn latency is 4–5s (p95) from end of user speech to next question audio starting. Aspirational is 3s.

**Why:**
Sub-2s latency would force adoption of a realtime voice API on day one, locking in vendor choice and reducing control over grounding. The 4–5s window is achievable with a standard DIY voice pipeline while still feeling like a "thoughtful pause" rather than broken.

**Tradeoff:**
The interaction will not feel as snappy as best-in-class voice assistants. Under microservices, inter-service network hops eat some of this budget — see decision 020.

**Revisit when:**
User testing shows the pause is a real product problem, or a realtime voice API becomes affordable and grounding-compatible enough to justify migration.

---

## 007 — Asynchronous repository ingestion with polling for status

**Decision:**
Repository ingestion runs asynchronously in the RAG service. The client polls the repository status endpoint (on the Core API) to detect completion. Users cannot start an interview until status is `ready`.

**Why:**
Ingestion for large repos may take minutes; blocking the HTTP request is not viable. Polling is far simpler than WebSocket/SSE for MVP and is acceptable given ingestion timescales.

**Tradeoff:**
Small extra request volume compared to push. Status updates are not instant.

**Revisit when:**
Ingestion times fall to under 10s (making polling wasteful), or the frontend adds a real-time update layer for other reasons.

---

## 008 — Partial reports on interrupted interviews; no live resumption

**Decision:**
Every turn (question + answer) is persisted as it happens. If the interview session is interrupted, the user receives a partial report from the completed turns. Live resumption of an in-progress session is not supported in MVP.

**Why:**
Fully transient interviews would punish users for accidents (refresh, network drop). Full resumption is a significant additional feature (state machine, session tokens, in-flight audio recovery) that is not core to MVP.

**Tradeoff:**
Users cannot pick up where they left off — they can only view what they've completed.

**Revisit when:**
User feedback indicates resumption is a common ask, or the underlying turn persistence makes resumption a small incremental change.

---

## 009 — Discard raw audio after transcription

**Decision:**
Raw user audio is discarded after transcription completes. The transcript is the persistent record of an answer.

**Why:**
Storing audio adds limited value (the transcript captures the semantic content) while adding storage cost and privacy concerns (voiceprint is biometric-adjacent).

**Tradeoff:**
Users cannot replay their own answers. Debugging STT errors is harder without the audio.

**Revisit when:**
A "replay my answer" feature becomes a real user need, or STT quality issues justify keeping audio for debugging.

---

## 010 — Single "Turn" entity, not separate Question and Answer

**Decision:**
A question and its answer are modeled together as a single Turn entity, not as two separate entities.

**Why:**
A question and its answer are always created and read together. Separate entities would add relational overhead and force joins for no functional benefit.

**Tradeoff:**
A Turn cannot cleanly represent a question that has been asked but not yet answered. This is handled with a status field on the Turn rather than separate entities.

**Revisit when:**
Questions and answers develop independent lifecycles (e.g., editing an answer, attaching multiple answers to one question).

---

## 011 — DIY voice pipeline over WebSocket for interview sessions

**Decision:**
The live interview session uses a WebSocket between the browser and the Voice service. The Voice service orchestrates the STT → retrieval → LLM → TTS pipeline itself, calling individual provider APIs, rather than relying on an integrated realtime voice API.

**Why:**
Full control over each stage — especially retrieval and prompting, which are critical to the grounding requirement. Higher learning value. Lower per-minute cost. The 4–5s latency target is achievable with this approach.

**Tradeoff:**
More code to write and maintain. Pipeline orchestration, streaming, reconnect logic, and error handling are all our responsibility. Latency depends on how well the stages are chained.

**Revisit when:**
DIY latency proves unreliably above the target, or a realtime voice API's grounding/tool-use capabilities and pricing improve enough to justify migration.

---

## 012 — 4-service microservices architecture

**Decision:**
RepoViva is built as 4 independently deployable services communicating over HTTP (and WebSocket for the interview session): Core API, RAG Service, Voice Service, Evaluation Service. All 4 share a single PostgreSQL database (see decision 021).

*This decision supersedes an earlier draft of decision 012 that proposed a modular monolith. That draft was revised after mentor confirmation that microservices is the intended architecture for this project.*

**Why:**
Explicit portfolio and learning goal: demonstrate hands-on microservices experience (service contracts, inter-service communication, independent deployment, service boundaries) as directed by the project mentor. The 4-service split reflects distinct responsibilities rather than fine-grained decomposition.

**Tradeoff:**
Higher operational complexity than a monolith. Inter-service network hops eat some of the interview turn-latency budget (see decision 006). Cold-start impact on free-tier deployment where multiple services must wake up. Time spent on service infrastructure is time not spent on AI-engineering depth.

**Revisit when:**
A specific service boundary proves painful and consolidation would materially improve delivery velocity, or a service's scaling profile diverges enough to justify further splitting.

---

## 013 — AI engineering depth is a first-class priority alongside microservices

**Decision:**
Even with a microservices architecture, the AI engineering work (retrieval strategy, RAG evaluation, grounding enforcement, prompt design, agent design if warranted) is treated as first-class capstone depth. Neither the microservices nor the AI dimension is sacrificed to the other.

**Why:**
Microservices architecture demonstrates system-design experience; AI engineering demonstrates the domain expertise the project is actually about. Both matter for the capstone.

**Tradeoff:**
Overall scope is larger than either purely-AI or purely-microservices variants. Requires disciplined "simple first, deepen incrementally" execution, per mentor's guidance.

**Revisit when:**
Timeline pressure forces prioritization; return here to decide explicitly which dimension to trim.

---

## 014 — Monorepo

**Decision:**
All code (all 4 services + frontend) lives in a single git repository, organized into per-service subdirectories (e.g., `core-api/`, `rag-service/`, `voice-service/`, `evaluation-service/`, `frontend/`).

**Why:**
Solo dev doesn't need the cross-team coordination isolation that separate repos help with. Simpler local development (one clone, one branch strategy). Shared config, shared CI, atomic cross-cutting changes across services. Independent deployment per service is still possible from a monorepo.

**Tradeoff:**
The repo will grow larger over time. Cannot easily grant a collaborator access to only one part.

**Revisit when:**
Team grows and independent deployment cadences emerge, or one part attracts open-source contribution independent of the others.

---

## 015 — Python 3.11+ with `uv` as package and environment manager

**Decision:**
All Python services run on Python 3.11 or newer. Dependency management, virtual environments, and lockfiles are handled by `uv` (from Astral).

**Why:**
Python 3.11 introduced meaningful performance improvements over 3.10 and is the current standard baseline for FastAPI projects. `uv` is significantly faster than `pip` and consolidates the roles of `pip`, `venv`, and `pip-tools` into a single tool with reproducible lockfiles.

**Tradeoff:**
`uv` is newer than `pip` and has less institutional familiarity. Some tutorials and CI templates still assume `pip` + `requirements.txt`.

**Revisit when:**
`uv` proves unreliable in a specific workflow (unlikely at current maturity), or a hosting/CI environment cannot support it.

---

## 016 — PostgreSQL with pgvector for both relational data and retrieval index

**Decision:**
A single Postgres database stores all relational data (users, repositories, interviews, turns, reports, encrypted OAuth tokens) and the vector representations used for code retrieval, via the `pgvector` extension.

**Why:**
One database means one connection pool per service, one backup strategy, one migration tool, and one hosting bill. `pgvector` is production-mature and eliminates the need for a separate vector DB service. Free-tier availability on Supabase and Neon, both of which include `pgvector`.

**Tradeoff:**
`pgvector`'s approximate-nearest-neighbor performance is not as fast as dedicated vector DBs (Qdrant, Weaviate, Pinecone) at very large scale. Not a concern at RepoViva's target of ~10 concurrent users and per-repo indexes.

**Revisit when:**
Retrieval latency exceeds the target despite tuning, or index size per repository grows beyond what `pgvector` handles well.

---

## 017 — React + Vite + TypeScript for the frontend

**Decision:**
Frontend is a React SPA built with Vite and written in TypeScript.

**Why:**
React was decided in the original brief. Vite is the current standard for React tooling — fast hot module reload, minimal config. Next.js would add SSR, routing conventions, and edge deployment complexity that RepoViva (a logged-in SPA with no SEO surface) does not need. TypeScript catches errors at build time, which matters more in a solo-dev project without code review.

**Tradeoff:**
TypeScript adds some upfront friction learning the type system. Vite is SPA-only — no built-in SSR, which is fine for this product.

**Revisit when:**
SEO or public marketing pages become important (not for MVP).

---

## 018 — Docker Compose for local Postgres; managed Postgres in production

**Decision:**
Locally, Postgres runs in a Docker Compose service. In production, a managed Postgres provider is used (specific provider — Supabase or Neon — deferred).

**Why:**
Local Docker Compose gives full control, works offline, and matches production's Postgres version exactly. Managed Postgres in production removes the burden of backups, TLS, patching, and monitoring.

**Tradeoff:**
Two environments to maintain (local Docker, cloud in prod). Small risk of config drift between them.

**Revisit when:**
Local dev friction outweighs the benefits, or provider lock-in becomes a concern.

---

## 019 — pytest + ruff (backend); Vitest + ESLint (frontend)

**Decision:**
Each Python service uses `pytest` for tests and `ruff` for both linting and formatting. Frontend uses `Vitest` for tests and `ESLint` for linting.

**Why:**
These are the current standard, boring, correct choices for each stack. `ruff` replaces the previous flake8 + black + isort combination with one fast tool. `Vitest` is Vite-native and faster than Jest. Setting these up from day one avoids painful retrofitting later.

**Tradeoff:**
Adds ~15 minutes of setup before writing feature code. Some rules will feel restrictive at first.

**Revisit when:**
A rule gets in the way often enough that muting it becomes tempting (fix the rule, don't disable the tool).

---

## 020 — 4-service split: Core API, RAG Service, Voice Service, Evaluation Service

**Decision:**
The 4 services are:

- **Core API** — GitHub OAuth, user CRUD, repository/interview/report metadata CRUD, session token issuance. The main REST entry point for the frontend.
- **RAG Service** — Repository ingestion (fetch from GitHub, parse, chunk, embed), retrieval queries at interview time. Owns the code index.
- **Voice Service** — Terminates the interview WebSocket, orchestrates the STT → RAG lookup → LLM → TTS pipeline for each turn, persists turns.
- **Evaluation Service** — Given a completed interview transcript, generates the final report.

**Why:**
Each service has a coherent, distinct responsibility. Core API sits between the frontend and the AI services, handling everything that is not strictly AI. RAG Service centralizes all repository knowledge. Voice Service owns the live-session state and orchestration. Evaluation Service isolates report-generation logic (which can be slow / async) from live latency-sensitive services.

**Tradeoff:**
Voice Service must call RAG Service during turns, adding a network hop that eats into the turn-latency budget. Evaluation Service could arguably live inside Core API, but keeping it separate gives room to run it async and scale it independently if reports get slow.

**Revisit when:**
An interview turn's cross-service latency proves impossible to bring under the 4–5s p95 target, or one service is shown to be trivial enough to collapse into another.

---

## 021 — Shared PostgreSQL database across all 4 services

**Decision:**
All 4 services share a single PostgreSQL database. Each service owns its own tables — no service directly reads or writes another service's tables. Cross-service data access goes through HTTP APIs, not through the database.

**Why:**
Strict per-service databases would multiply cost (4× free-tier DB usage) and operational overhead without clear benefit at the current scale (~10 concurrent users). Shared-DB with strict per-service ownership is a well-established pragmatic pattern for early-stage microservices.

**Tradeoff:**
Not the "purest" microservices pattern. Coupling risk: a schema change in one service's tables could theoretically affect another. Mitigation: strict rule that no service reads another's tables directly — always via HTTP.

**Revisit when:**
A service needs to scale its database independently, per-service tenancy/data-isolation requirements emerge, or the shared-DB coupling causes real problems in practice.

---

## 022 — Frontend talks to Core API (REST) and Voice Service (WebSocket) directly; no API gateway

**Decision:**
The React frontend calls Core API directly for REST endpoints (auth, CRUD) and connects directly to Voice Service via WebSocket for the live interview. No API gateway or BFF layer sits in front of the services.

**Why:**
An API gateway would add operational complexity and latency without clear benefit at MVP scale. Frontend knowing 2 endpoints is manageable. Session tokens issued by Core API are validated by Voice Service on WebSocket connect — this maintains the security boundary without requiring a proxy.

**Tradeoff:**
Frontend has knowledge of the internal service topology. If a 3rd frontend-facing service is added later, the client-side gets more complex. Rate limiting or unified auth checks that would normally live in a gateway must be implemented in each service.

**Revisit when:**
A 3rd frontend-facing service is added, or cross-cutting concerns (rate limiting, unified auth checks) become painful to duplicate.

---

## 023 — Repository Service (renamed from RAG Service)

**Decision:**
The second service is named Repository Service (folder: `repository-service/`), not RAG Service. Existing decisions 012, 020, 021, and 022 that reference "RAG Service" are amended by this decision — the responsibilities described there are unchanged, only the name.

**Why:**
"Repository Service" describes the service's responsibility — owning everything about a connected repository's code and its searchable representation. "RAG Service" names it after one technique it happens to use. If a second retrieval strategy is added alongside RAG later, or if RAG is replaced entirely, the responsibility-based name still fits; the technique-based name would lie.

**Tradeoff:**
Historical references to "RAG Service" in early decisions must be mentally translated. Slightly longer name.

**Revisit when:**
The service's responsibility narrows to something more specific than "repository knowledge," at which point a more specific name would be honest.

---

## 024 — Core API owns repository ingestion status; Repository Service reports via authenticated callback

**Decision:**
The `repositories.status` field is owned by Core API. Repository Service does not write to it directly. When Repository Service's ingestion job progresses, it sends an authenticated HTTP callback to Core API, which validates the transition and updates the status.

This closes the TBD in the ingestion data flow (previously "via a callback or by writing to a shared status field — TBD").

*Note: implementation of the callback receiver was deferred by decision 028. This decision remains valid as design; only its implementation is postponed until real ingestion clarifies the actual event shape and volume.*

**Why:**
Status *reads* are frequent — the frontend polls every couple of seconds while ingestion runs. Status *writes* are rare — only a handful per ingestion. Putting the network hop on the rare event (callback) and keeping the hot read path in-process on Core API minimizes cross-service traffic. It also preserves the per-service table ownership rule from decision 021 — only Core API writes to its own `repositories` table.

**Tradeoff:**
Core API must expose an authenticated internal endpoint that another service can call. Callbacks can be lost, delayed, or duplicated over HTTP, which forces us to think about idempotency and retry semantics (see decision 025).

**Revisit when:**
Poll load from the frontend becomes a bottleneck, or a real-time push channel (SSE, WebSocket) makes polling obsolete.

---

## 025 — Event-style callbacks with idempotency keys

**Decision:**
Repository Service reports progress as discrete events (`ingestion.started`, `ingestion.completed`, `ingestion.failed`), not as state snapshots. Every event carries a unique `event_id` (UUID v4). Core API deduplicates by `event_id` — replays return `409 Conflict` without side effects.

*Note: implementation deferred by decision 028. Design remains valid.*

**Why:**
The ingestion pipeline will grow beyond simple state transitions — sub-stage progress (fetching, parsing, chunking, embedding, indexing), file counts, warnings — and event-style scales to that naturally. Snapshot-style would need to be extended awkwardly once the pipeline gains real stages. Event IDs make HTTP-based at-least-once delivery safe by giving the consumer a stable dedup key.

**Tradeoff:**
Core API must know the state machine (which events are legal from which state) and must persist seen `event_id`s to dedupe. Slightly more schema surface than snapshot-style would require today.

**Revisit when:**
The event schema stabilizes and a shared event bus (Redis Streams, NATS, Kafka) would be justified by multiple consumers or a real audit-trail requirement.

---

## 026 — Repository ingestion state machine (MVP)

**Decision:**
Repository ingestion has four states: `queued`, `in_progress`, `ready`, `failed`. Legal transitions:

- `queued → in_progress` (via `ingestion.started`)
- `in_progress → ready` (via `ingestion.completed`)
- `in_progress → failed` (via `ingestion.failed`)

Additional transition applied by Core API itself (not via callback):

- `queued → failed` — set immediately when the trigger call to Repository Service fails at creation time. See decision 028 and the `create_repository` handler.

No sub-states within `in_progress` for MVP. Retry behavior (whether a failed row can be retried in place or a new row is created) is deferred until retry is implemented.

**Why:**
Four states cover every case the frontend needs to render today. Sub-states (fetching, parsing, chunking, embedding) will matter only once the real pipeline exists and users need visibility into stages; adding states later is cheap, subdividing a state that's already shipped is harder.

**Tradeoff:**
The frontend cannot show granular progress inside `in_progress`. Users see an opaque "processing" state that may last a while.

**Revisit when:**
The real ingestion pipeline is implemented and per-stage visibility is worth exposing.

---

## 027 — HMAC-SHA256 authentication for internal service-to-service calls

**Decision:**
Every internal service-to-service HTTP call is authenticated with an HMAC-SHA256 signature. The sender computes `HMAC_SHA256(secret, timestamp + "." + request_body)` and sends two headers:

- `X-Repoviva-Timestamp` — Unix seconds
- `X-Repoviva-Signature` — `sha256=<hex digest>`

The receiver rejects requests older than 60 seconds and verifies the signature with a constant-time comparison (`hmac.compare_digest`). A single shared secret (`INTERNAL_HMAC_SECRET`) is used across all internal calls in both directions.

Per the "write it twice, deliberately" approach chosen in slice 2, each service implements the HMAC module independently — the wire format is the contract, not the code. Same wire format, independent implementations.

**Why:**
Our internal callbacks are structurally webhooks, and HMAC is the pattern the webhook industry has converged on (GitHub, Stripe, Slack, Shopify). It provides authenticity, body integrity, and — with the timestamp in the signed payload — replay protection, without the operational cost of mTLS or the machinery of an OAuth server. A 60-second freshness window is honest for services on the same Docker network; clock skew is negligible, and no legitimate callback takes that long.

**Tradeoff:**
Symmetric secret — either service can forge signatures for the other, so this proves "one of us sent it," not "specifically Repository Service sent it." Fine for a two-party trust boundary. A leaked secret compromises both directions until rotation. No per-caller identity or scopes, so we can't do fine-grained authorization on internal calls.

**Revisit when:**
A third internal caller is added and per-caller identity matters, secret rotation becomes a real operational need, or the threat model requires asymmetric authentication (e.g., mTLS between services deployed across untrusted networks).

---

## 028 — Defer async status callbacks; use HTTP trigger only, revisit when real ingestion exists

**Decision:**
Core API triggers Repository Service ingestion via a synchronous HTTP call — implemented in slice 2 step 4. Repository Service accepts the trigger, returns `202 Accepted`, and (for now) does no further work.

Status reporting from Repository Service back to Core API is **deferred** — not built in the current slice. The design work for event-style HTTP callbacks (decisions 024, 025, 026) is preserved as documented option, but implementation is postponed until real ingestion exists and we can evaluate:

- Whether a message broker (Kafka, NATS, Redis Streams) is justified by real requirements (multiple consumers, high throughput, replay), or
- Whether HTTP callbacks remain the right choice for one consumer and a handful of events per ingestion.

Decisions 024–026 remain valid as *design*; only their implementation is deferred.

Behavior when the trigger call fails: Core API marks the just-created repository row `failed` immediately, with an `error_message` describing the trigger failure, and returns 201 to the user. Rolling back the row (making the failure invisible) or leaving the row silently in `queued` were both considered and rejected.

**Why:**
Building the callback receiver, event dedup, and state-transition validation now — before real ingestion exists to test it against — would produce code that has a meaningful chance of being rewritten once real ingestion clarifies the actual event shape and volume. Building HTTP callbacks now, only to swap them for Kafka later "because microservices," would be the exact anti-pattern the project mentor's guidance warns against: choosing a technology for portfolio appearance rather than because a specific problem justifies it.

The trigger itself stays HTTP. Fire-and-forget triggers are a poor fit for message queues (which are optimized for durable multi-consumer streams), and the HTTP trigger implementation is not throwaway even if async messaging is added later. So decision 027's HMAC authentication still applies to the trigger call.

**Tradeoff:**
- Repository ingestion status is unobservable from Core API until this is revisited. The frontend cannot show "still processing" or "failed for a real reason" for a real ingestion; it can only show `queued` (or `failed` if the trigger itself failed).
- The design work in decisions 024–026 is temporarily "dark" — described but not exercised. If the design turns out to be wrong once real ingestion exists, we'll find out through rework, not through running code.
- Slice 2's original vision (see-a-full-cycle end-to-end) is not delivered in this slice.

**Revisit when:**
Real ingestion is implemented in Repository Service. At that point:
1. Assess actual event volume, number of consumers, and replay requirements.
2. Choose between HTTP callbacks (decisions 024–026 as-is) or a message broker (which would supersede decisions 024–026).
3. Implement whichever is justified.

## 029 — HTTP callbacks with loose state machine; no dedup for MVP

**Decision:**
Revisits decision 028, now that real ingestion exists in Repository Service.

Ingestion status is reported from Repository Service to Core API via
HMAC-signed HTTP callbacks (`POST /internal/v1/repositories/{id}/events`),
implementing the design in decisions 024–026. Repository Service emits
`ingestion.started` before fetch, `ingestion.completed` on success, and
`ingestion.failed` on any exception — with the git stderr (or unexpected
exception message) carried in `data.error_message`.

Core API applies a **loose state machine** on receipt: any target
transition is accepted from `queued` or `in_progress`; terminal states
(`ready`, `failed`) reject further events with 422. This defends
against out-of-order and dropped events without demanding strict
event ordering.

**Deduplication by `event_id` is deferred.** Repository Service does
not retry failed callbacks; Core API does not persist processed
`event_id`s. `emit_event` logs and swallows network/HTTP errors —
a lost callback leaves the row in whatever state it was last set to,
and the frontend surfaces `queued` or `in_progress` opaquely until the
next callback (or until the ingestion is retried).

**Why:**
For MVP (single consumer, ~3 callbacks per ingestion, services on the
same Docker network), the realistic drop rate is essentially zero, and
building retry+dedup infrastructure ahead of any observed failure
would be exactly the speculative machinery the project's guidance
warns against. The `event_id` field is already in the wire format, so
adding dedup later is a table migration plus a 20-line receiver
change — the sender doesn't need to change.

The loose state machine was chosen over strict ordering because HTTP
does not guarantee event delivery order under load, and being tolerant
of out-of-order events (e.g. `ingestion.completed` arriving before
`ingestion.started` if the first callback is retried) keeps the
state visible to the frontend even when the network misbehaves.

**Tradeoff:**
- A callback dropped by network failure leaves the DB row stale until
  the next event lands. Users may see `in_progress` for a completed
  ingestion, or `queued` for one in progress.
- The loose state machine accepts events that a strict machine would
  reject; a bug in Repository Service that sent `ingestion.completed`
  before `ingestion.started` would be silently accepted. Chosen
  anyway because real-world event-order drift from HTTP is more
  likely than a bug of that specific shape.
- Terminal states are unchangeable via callback. Retry semantics
  (whether a `failed` row can be resurrected) are still deferred as
  in decision 026 — a retry endpoint that resets the row to `queued`
  would live on Core API, not go through the event pipeline.

**Revisit when:**
- Observed callback drop rate exceeds ~1% of ingestions, or a
  single dropped callback in production causes user confusion — at
  that point add sender-side retry with exponential backoff, and
  receiver-side dedup by `event_id` (via a `processed_events` table
  as sketched in the shared-DB storage note in `architecture.md`).
- Callback event volume grows past a few per ingestion (per-stage
  progress like `fetch.complete`, `chunk.complete`, `embed.complete`)
  and observability of individual event delivery becomes valuable.
- A message broker becomes justified by a second consumer of the
  same events (e.g. an audit-log service or an analytics pipeline).

---

## 030 — Voyage AI voyage-4-lite as the embedding provider

**Decision:**
Repository Service uses Voyage AI's `voyage-4-lite` as the embedding
model for both indexing (Repository Service) and query-time embedding
(Voice Service). Vector dimension is 1024. The API key
(`VOYAGE_API_KEY`) is provided via environment variables and consumed
through CocoIndex's LiteLLM integration
(`cocoindex.ops.litellm.LiteLLMEmbedder("voyage/voyage-4-lite")`).

*Correction (2026-09-16, slice 3 step 2 implementation): the API
originally named here — `cocoindex.functions.EmbedText` /
`cocoindex.LlmApiType.VOYAGE` — does not exist in the installed
CocoIndex version (1.0.23). It was written against a
different/expected API surface before real implementation. The
actual model choice, cost, and privacy reasoning below are
unaffected; only the integration mechanism changes, and the "Native
CocoIndex integration" bullet below is corrected to match.*

**Why:**
- **Free allocation suited to development.** Voyage grants every
  account a lifetime 200M free tokens on the voyage-4 generation,
  verified against Voyage's own pricing page (Sep 2026). A typical
  portfolio repo produces ~100k–400k tokens per ingestion, so 200M
  covers a very large amount of iteration and re-ingestion during
  development without daily quota resets. **Caveat confirmed during
  slice 3 step 2 implementation:** an account with no payment method
  on file is throttled to 3 requests/minute and 10K tokens/minute
  regardless of remaining free-token balance — CocoIndex's embedder
  treats HTTP 429 as retryable and backs off silently rather than
  failing fast, so indexing a real repo under this limit appears to
  hang rather than error. Adding a payment method lifts the limit
  (the free-token grant still applies). Worth doing before any
  real-repo ingestion test, not just a quota-exhaustion concern.
- **Low paid cost at overflow.** $0.02 per million tokens beyond the
  free grant. Even ingesting hundreds of large repos stays inside a
  handful of dollars.
- **Better privacy posture for private repositories.** RepoViva
  supports private GitHub repos (decision 001). Voyage's terms do
  not include a training-on-inputs clause. Gemini's free tier does
  ("free-tier data may be used to improve Google's products"), which
  would be a real problem the moment a user connects a private repo.
  Voyage removes that landmine.
- **Native CocoIndex integration.** `cocoindex.ops.litellm.LiteLLMEmbedder("voyage/voyage-4-lite")`
  is a one-liner in the flow file, implements `VectorSchemaProvider`
  for the pgvector column, and needs no custom `@coco.fn` embedder —
  CocoIndex's own embedding integration goes through LiteLLM, not a
  separate Voyage-specific function.
- **Shared vector space across the voyage-4 family.** If quality
  needs push us to `voyage-4` ($0.06/M, same 200M free grant) or
  `voyage-4-large` ($0.12/M), we can switch models without
  re-indexing — the vectors from any voyage-4 model live in the same
  space per Voyage's docs.

**Alternatives considered:**
- **Gemini `text-embedding-004`** (native CocoIndex support,
  free tier, 768-dim). Rejected primarily because the free tier's
  data-for-training clause conflicts with our private-repo support.
  Secondary concerns: Google has cut free-tier quotas without
  notice historically (50–80% reductions in Dec 2025); the newer
  `gemini-embedding-001` reportedly returns a quota of 0 for free-
  tier accounts, so we'd be locked to the older model; and Google
  no longer publishes exact free-tier per-model rate limits in
  their public docs, only in AI Studio for each account.
- **Voyage `voyage-code-3`** (code-tuned, would have been the
  obvious pick). Rejected because it is not on Voyage's free tier
  despite the name — their pricing table places it in "older
  models" at $0.18/M with zero free allocation. `voyage-4-lite`
  costs 9× less and is on the free grant.
- **OpenAI `text-embedding-3-small`.** No ongoing free tier; new
  accounts get a small credit that expires. Removed on cost
  grounds during development.
- **Local `sentence-transformers/all-MiniLM-L6-v2`** (CocoIndex's
  canonical example). Rejected because loading the model in
  both Repository Service and Voice Service doubles the RAM cost
  on small hosts, CPU inference is slow, and cold-start image
  size grows.

**Tradeoff:**
- **Model choice is now sticky.** Changing embedding provider or
  model dimension later requires re-embedding every chunk of every
  ingested repository. There's no cheap "swap the model" path once
  we have real data. This is not unique to Voyage — it's true of
  any embedder — but it's worth naming as the cost of picking now.
  Voyage's shared vector space within the voyage-4 family softens
  this for intra-family upgrades but not for switching providers.
- **External dependency.** Ingestion and query both fail if
  Voyage's API is down. For MVP scale (~10 concurrent interviews),
  this is acceptable; if downtime bites, we can revisit with a
  local fallback.
- **Free-tier grant is per-account, not renewable.** Once the 200M
  is spent, all embedding is paid. Not a problem at MVP scale, but
  a real cost lever if RepoViva ever gains real users.

**Revisit when:**
- Voyage's free grant is exhausted and paid cost becomes a
  meaningful operational expense.
- Retrieval quality on real interviews is materially worse than a
  code-tuned alternative would offer (evaluate against
  `voyage-code-3` paid, or `voyage-4` / `voyage-4-large`).
- Voyage's terms of service or pricing structure change in a way
  that reopens the trade.

---

## 031 — Repository Service owns `code_chunks` DDL; CocoIndex mounts it as user-managed

**Decision:**
The `code_chunks` table (and its pgvector index) is created by
Repository Service itself, via `sql/schema.sql` applied through
`db.apply_schema()` in the FastAPI lifespan — not by CocoIndex.
`indexing/flow.py` mounts the table with
`postgres.mount_table_target(..., managed_by=ManagedBy.USER)`, so
CocoIndex's per-repository indexing App (one App per `repository_id`,
per `indexing/app.py`) only reconciles rows against the table; it
never issues `CREATE TABLE`/`ALTER TABLE`/`DROP TABLE`.

The table's primary key is `(repository_id, id)`, not bare `id`.

**Why:**
Implementing and testing real indexing (slice 3 step 2) surfaced two
bugs in the original design, both invisible until a *second*
repository was actually indexed against the same table:

- **`DuplicateTableError` on every repository after the first.**
  Each `repository_id` gets its own CocoIndex App with independent
  tracked state. A fresh App has no record of a table a *different*
  App already created, so on its first mount it issued a plain
  `CREATE TABLE` (CocoIndex's own state-diffing logic only adds
  `IF NOT EXISTS` when its *own* tracked history shows a prior
  version of the table) — which fails against a table that
  physically exists already. This would have broken real ingestion
  the moment a second repository was ever indexed.
- **Silent cross-repository data loss.** CocoIndex's `generate_id()`
  is a sequential counter scoped per App, starting at 1 — not
  globally unique. With one App per repository and a bare `id`
  primary key, two repositories' first chunk both land on `id=1`.
  Row writes are `INSERT ... ON CONFLICT (id) DO UPDATE`, so the
  second repository indexed did not error — it silently overwrote
  the first repository's row, including its `repository_id`. This
  was found only by querying Postgres after indexing two repositories
  in sequence, not from any exception or log line.

Making the application own the DDL (rather than CocoIndex) fixes the
first bug directly: the table already exists before any App ever
mounts it, so there is no "first App to see it" race. Widening the
primary key to `(repository_id, id)` fixes the second: two
repositories' colliding `id=1` no longer collide as *rows*, since
Postgres now treats `(repo-a, 1)` and `(repo-b, 1)` as distinct keys.

**Alternatives considered:**
- **One shared CocoIndex App for all repositories** (source_dir and
  repository_id as row-level data instead of App identity). Would
  sidestep both bugs structurally, but changes the ingestion
  execution model (one long-lived App vs. one per ingestion run) and
  is a bigger change than the bug warranted. Rejected for now —
  revisit if per-repository App overhead becomes a real cost.
- **UUIDs instead of `generate_id()` for `id`.** Would give globally
  unique IDs without a composite key, but throws away CocoIndex's
  built-in memoization (`generate_id` returns the same id for the
  same dependency value across incremental re-indexing runs, which
  is what makes re-ingesting an unchanged file a no-op). Rejected —
  the composite key gets uniqueness without losing that.

**Tradeoff:**
- `table.declare_vector_index(column="embedding")` in `flow.py`
  still runs on every App's `app_main`, independent of
  `managed_by`. It reconciles via `DROP INDEX IF EXISTS` +
  `CREATE INDEX`, so it's idempotent and never errors, but a fresh
  App (a repository's first-ever index run) has no tracked record of
  the index either, so it always rebuilds it — a wasted
  drop+recreate of the shared `ivfflat` index on every new
  repository's first run. Accepted for now since it's a correctness
  no-op, not a correctness bug, and repositories are not indexed
  concurrently at MVP scale.
- `sql/schema.sql` and `indexing/schema.py`'s `CodeChunk` dataclass
  must be kept in sync by hand — there is no single source of truth
  generating both. A mismatch would surface as a Postgres error on
  the first write after a `CodeChunk` field changes without a
  matching `schema.sql` update.
- DDL ownership is now split from the CocoIndex flow that most
  directly depends on its shape, which is slightly less
  discoverable than “the flow file creates its own table.” Comments
  in both `flow.py` and `schema.sql` cross-reference each other to
  mitigate this.

**Revisit when:**
- A second CocoIndex-backed table is added and the same
  `managed_by=ManagedBy.USER` + hand-written DDL pattern needs to be
  repeated — worth extracting a shared helper at that point.
- Per-repository Apps' vector-index rebuild-on-first-run cost becomes
  measurable (e.g. large repositories or many repositories indexed
  concurrently) — consider pre-creating the index in `schema.sql` in
  a way CocoIndex recognizes as already matching, or moving to a
  single shared App (see alternatives above).
- Repository Service moves to its own Postgres schema (per
  `architecture.md`'s stated "one schema per service" model, not yet
  implemented — `code_chunks` currently lives in `public`) — `sql/schema.sql`
  and `apply_schema()` would need a schema-qualified table name.

---

## 032 — Retrieval endpoint: hand-rolled SQL, no commit pinning, 404/409 collapsed to empty 200

**Decision:**
`POST /internal/v1/repositories/{repository_id}/retrieve` (Voice Service's
only way to pull code context during an interview) is implemented as one
hand-written asyncpg query against `code_chunks`, not a vector-store
library. It takes `repository_id` as `int` in the path (stringified once,
same as `/ingest`) and does not accept or filter on `commit_sha`. It always
returns `200` — `{"chunks": [...]}`, empty if nothing matches — never `404`
or `409`.

**Why:**
- **No LangChain/vectorstore library.** The query is one `ORDER BY
  embedding <=> $1 LIMIT $n` with two extra filters; there's no chain,
  agent, or multi-step retrieval strategy that would justify the
  abstraction. More importantly, `code_chunks`' schema is owned by this
  service specifically to get exact control over its primary key and
  column shape (decision 031) — a generic vectorstore wrapper would either
  fight that shape or stand up a second, divergent store. Query-side
  embedding reuses the same `EMBEDDER` (`indexing/embedder.py`) ingestion
  already uses, called directly — no flow/App machinery needed for a
  single ad-hoc embed.
- **No `commit_sha` filter.** No re-ingestion path exists yet anywhere in
  the codebase (`ingest_trigger` has no "already ingested" check), and an
  interview session references only `repository_id`
  (`POST /v1/interviews body: { repository_id }` — no commit). Filtering
  by `repository_id` alone is therefore both sufficient and honest about
  what the system currently supports.
- **404/409 collapsed to 200 + empty array.** Repository Service has no
  local record of ingestion status — that state lives entirely in Core
  API, reached only via outbound HMAC callbacks this service sends, never
  queried back (decision 029). It genuinely cannot tell "unknown
  `repository_id`" apart from "ingestion still running" apart from "done":
  CocoIndex writes `code_chunks` rows per-file as ingestion proceeds, so
  even a nonzero row count doesn't prove completion. Rather than fake a
  distinction it can't actually make, the endpoint always returns `200`.
  Core API already gates `POST /v1/interviews` on repo status `ready`, so
  in the intended flow this endpoint is never called before ingestion is
  done.

**Alternatives considered:**
- **LangChain's `PGVector` vectorstore.** Rejected — see above; it wants
  to own the table shape this service deliberately owns itself.
- **404 on zero rows, 200 otherwise.** Gives one error signal for
  obviously-wrong `repository_id`s, but silently returns partial results
  (200) if ever queried mid-ingestion, with no way to flag that case.
  Rejected as a false sense of precision — decided directly with the user
  in favor of the simpler always-200 contract.
- **Repository Service tracks its own ingestion-status marker** (new
  table/column) so it could answer 404/409 accurately. Rejected — would
  duplicate state Core API already owns, contradicting decision 021's
  strict per-service table ownership, for a distinction the intended
  caller (Core API-gated interview creation) doesn't need.

**Tradeoff:**
- **Mixed `commit_sha` per repository is a live latent gap, not yet
  triggered.** `index_file` is `memo=True` and `id` is content-derived
  specifically so re-ingesting an unchanged file is a no-op (decision
  031). If a repository is ever re-ingested at a new commit, unchanged
  files' rows keep their original `commit_sha` while changed files' rows
  get the new one — one `repository_id` could end up with chunks stamped
  from two different commits, invisibly to this endpoint. Not a problem
  today because there is no re-ingestion trigger yet; becomes real the
  moment one is built.
- **A stale or wrong `repository_id` returns an empty result, not an
  error.** Voice Service (or a caller upstream of it) has no signal from
  this endpoint alone to distinguish "no relevant chunks for this query"
  from "this repository was never ingested." Acceptable because Core API
  is the source of truth for repo status and gates interview creation on
  it already.

**Revisit when:**
- A re-ingestion endpoint is built — resolve the mixed-`commit_sha`
  question then (pin to the ingesting commit at read time, or force a
  full re-embed on every re-ingest so all rows for a repo always share one
  commit).
- Voice Service reports confusing-empty-results incidents that a 404
  would have caught faster — revisit the always-200 contract, most likely
  by adding the local status tracking alternative above rather than
  querying Core API synchronously on the retrieval hot path.

---

## 033 — Exact vector search, a 6,000-chunk repository cap, and no translated docs

**Decision:**
- **Exact search, no ANN index.** `code_chunks` has no approximate-nearest-
  neighbour index on `embedding`. `retrieval/search.py` narrows to one
  repository via `PRIMARY KEY (repository_id, id)`, computes cosine
  distance for every row of that repository, and sorts. `sql/schema.sql`
  drops the old `code_chunks__vector__embedding` ivfflat index;
  `indexing/flow.py` no longer calls `table.declare_vector_index()`.
- **Repository cap: 6,000 chunks, chosen conservatively** (`MAX_REPO_CHUNKS`,
  `indexing/runner.py`; see "the binding budget" below for what it is and
  is not derived from). `run_indexing()` counts chunks in a local
  pre-pass — same `PATH_MATCHER`, same `split_source()` as the flow, no
  API calls — and raises `RepositoryTooLargeError` **before any embedding
  call** if the count exceeds the cap. The orchestrator reports it as
  `ingestion.failed` with `"repository too large: N chunks (limit 6,000)"`.
- **Translated docs are not indexed.** `EXCLUDED_PATTERNS` in `flow.py`
  drops `**/docs/<language code>/**` (explicit list of codes, so ordinary
  `docs/api/`, `docs/guide/` stay) and Docusaurus `**/i18n/**`.

This supersedes the vector-index tradeoff noted in decision 031. No HNSW.

**Why — the index:**
The ivfflat index had three defects, in order of severity:

1. **Built on an empty table.** `apply_schema()` created it at startup,
   before any repository existed. ivfflat trains k-means centroids at build
   time; with no rows they are meaningless. Per-repository ivfflat indexes
   would repeat the bug — each also built on zero rows.
2. **`ivfflat.probes` defaulted to 1** — one list of 100 probed. Never set.
3. **Post-index filtering.** Every query filters on `repository_id`, but
   the ANN index is scanned first and the `WHERE` applied afterwards, so
   with many repositories fewer than `top_k` rows survive.

Without an ANN index pgvector does exact search: 100% recall by
construction, nothing to tune, no empty-table trap.

**Why — the measurements:**
Local docker-compose Postgres 16 + pgvector 0.8.6 on a dev laptop,
2026-09-30, `scripts/measure_search.py`, `top_k=10`. Three repositories
chosen as small, typical, and stress; the stress point is FastAPI with
translations removed (`14-en`: repository 14's rows minus non-English
docs, same embeddings), with full FastAPI as an out-of-scope reference.

| Repository | Role | Chunks | First query (ms) | Warm median (ms) | Warm p95 (ms) | Plan |
|---|---|---:|---:|---:|---:|---|
| missLaiba22/artisan-marketplace | typical user repo | 549 | 88 / 102 | 9 / 13 | 11 / 16 | PK bitmap scan |
| pallets/flask | small OSS | 842 | 333 / 40 | 13 / 12 | 22 / 14 | PK bitmap scan |
| fastapi, translations removed | stress | 7,169 | 103 / 128 | 86 / 87 | 124 / 121 | seq scan |
| fastapi, full | out of scope | 22,333 | 1,462 / 300 | 254 / 223 | 340 / 287 | seq scan |

*Sample counts and what they do and do not show:*
- **Warm:** 20 sequential runs per repository per pass, two passes (both
  shown, `pass 1 / pass 2`). p95 of 20 samples is the 19th-slowest value —
  indicative, not a tight tail estimate.
- **First query:** one sample per pass (n=2). This is the first query on
  a fresh connection, **not a controlled cold start** — no Postgres
  restart, OS page cache not dropped — so it is a lower bound on true cold
  latency. The one genuinely cold observation is full FastAPI immediately
  after ingestion: **1,757 ms** execution, `read=15289` buffers from disk.
- **One query vector per repository** (its first chunk's embedding).
  Sufficient for latency because exact search scores every row regardless
  of the query; it says nothing about retrieval quality (see recall below).
- Cost is linear: **~11–12 µs per chunk** above ~1,000 chunks, dominated by
  reading out-of-line (TOAST) 4 KB vectors, not by distance maths. Small
  repositories use the primary-key index, so their cost is independent of
  other repositories' data.

*Recall@5 of the translation exclusion* (`evals/recall_eval.py`, golden
set `evals/golden/fastapi.json`, per-query output in `evals/results/`): 20
interview-style questions about FastAPI, relevance sets (files/paths)
written before any results were seen; a docs hit counts in any language.

| Variant | Recall@5 | Strict (code/English only) | MRR | Top-5 slots taken by translations |
|---|---:|---:|---:|---:|
| fastapi, full | 90% | 75% | 0.80 | 71 / 100 |
| fastapi, translations removed | 95% | 95% | 0.87 | 0 / 100 |

Exclusion improved every metric: in the full index, translations of the
same page filled the top 5 (e.g. OAuth2 question: five Russian / Japanese
/ Ukrainian copies, and `fastapi/security/oauth2.py` absent). The one miss
in the excluded variant is a gap in the answer key
(`docs/en/docs/reference/parameters.md` is relevant but was not listed);
it misses in both variants equally. 20 queries on one repository: the
direction is clear, the percentages are not precise — one query is 5
points. A re-run of the full index gave strict 70% (not 75%) and 72 noise
slots: Voyage query embeddings vary slightly between calls and reorder
near-identical translated pages. Recall@5 and MRR reproduced exactly.

The headline is the *strict* column: on the full index, 75% → 95% on code
and English docs, with 71 of 100 top-5 slots spent on translations. Nothing
in the codebase — no test, log, or error — would have shown this; only an
eval did.

**Why — the binding budget:**
Of the constraints on retrieval — recall, Voyage cost, storage, latency —
latency is the one that binds. Recall is 100% of exact by construction;
storage and cost are small at this scale.

- The interview turn target is **4–5 s p95, 3 s aspirational**
  (`architecture.md`). Retrieval is sequential on that critical path —
  the LLM cannot start until context is retrieved — at session start
  (opening question) and after every answer.
- The rest of the turn (STT, LLM, TTS, inter-service hops) is external
  and not under this service's control. Retrieval is the one step fully
  under our control, so it gets a small fixed allotment: **100 ms p95**,
  ~3% of the aspirational 3 s.
- It is a **p95** budget, not a median one, because the turn target is
  itself p95 and an interview has many turns, so each session hits the
  tail repeatedly. At the measured ~12 µs/chunk the *median* reaches
  100 ms near 8,000 chunks, but p95 runs ~1.4× the median and reaches it
  near **6,000** — hence the cap. (An earlier median-based estimate put
  the threshold at 8,000; that was the wrong percentile.)
- Cold reads make the first turn the worst one: the opening-question
  retrieval is exactly when a repository's rows are least likely to be
  cached. Keeping repositories small keeps that cold read bounded too.

**What the cap is — and is not — derived from.** The 6,000 figure is
derived from the 100 ms retrieval *sub-budget*, which is self-imposed. It
is **not** derived from measured user-visible latency. Against the turn
budget itself the cap is conservative by a wide margin: 7,169 chunks costs
~120 ms p95 warm, ~20 ms over the sub-budget, in a 4,000–5,000 ms turn where
the LLM call dominates by roughly thirty times. The number that could
actually justify a cap is **cold** latency on the opening turn, and that
is unmeasured: the "first query" column above is not a true cold start.
6,000 is therefore a deliberately conservative choice, kept because
rejecting early is cheap to relax later, while silently slow first turns
are hard to notice. It is not a derived limit.

Under this budget, a typical user repository (549 chunks, p95 ~15 ms)
has ~10× headroom. The tail — very large or docs-heavy repositories — is
a product-scope question, not an index question: rejecting it with a
clear error is cheaper and more honest than making every query approximate.

**Alternatives considered:**
- **HNSW on the shared table** (`declare_vector_index(method="hnsw")`,
  matching `schema.sql`, `hnsw.ef_search` / `hnsw.iterative_scan` in
  `search.py`). No training step, so it suits incremental ingestion, and
  iterative scan mitigates post-filtering. Rejected for now: it trades
  recall on every query to serve repositories outside the product's
  target, and adds tuning and a recall-verification burden.
- **Per-repository partial indexes.** Rejected: many distinct
  `repository_id` values means one index object per repository created by
  DDL on the ingestion path; pgvector's guidance is partial indexes for a
  few filter values, partitioning for many. Each would also be ivfflat
  built on an empty repository.
- **Partitioning by `repository_id`.** Structurally right for this access
  pattern, but a large change to a table CocoIndex writes into.
- **Cap check inside `index_file`.** Rejected: files are indexed in
  parallel and embed as soon as they are split, so the cap would trip only
  after thousands of paid Voyage calls.

**Tradeoff:**
- **FastAPI is rejected.** Even with translations removed it has 7,169
  chunks — a clean, legitimate repository refused to protect a
  self-imposed sub-budget by ~20 ms. Accepted for now as the cost of a
  conservative cap; see "Revisit when".
- **The cap is a measured number, coupled to everything that produced
  it.** `MAX_REPO_CHUNKS = 6_000` is valid only for: this hardware class,
  1024-dim `voyage-4-lite` vectors, `top_k=10`, `CHUNK_SIZE=1000` /
  `CHUNK_OVERLAP=200`, the current `INCLUDED_PATTERNS` /
  `EXCLUDED_PATTERNS`, and exact search. Changing any of them changes
  either the chunk count per repository or the cost per chunk, and the
  cap silently becomes wrong. Nothing enforces this coupling; re-run
  `scripts/measure_search.py` (latency) and `evals/recall_eval.py`
  (quality) after any such change and re-derive the cap.
- The cap and the retrieval method are coupled too: under an ANN index the
  latency reason for the cap disappears, leaving only Voyage cost and
  retrieval quality as reasons to limit repository size.
- `count_chunks()` is deliberately coupled to the flow (shared
  `PATH_MATCHER` and `split_source()`); verified to match indexed counts
  exactly on all three repositories (549, 842, 7,169), and kept matching
  by `tests/test_indexing_flow.py`, which runs the real CocoIndex flow
  (fake embedder) and asserts rows written == `count_chunks()`. It reads files with
  `utf-8-sig` while CocoIndex auto-detects encoding, so a non-UTF-8 file
  could count slightly differently.
- The pre-pass runs after cloning, so a too-large repository still costs
  a clone (~40 s for FastAPI) before being rejected; it costs no Voyage.
- The index is controlled in two places: `schema.sql` drops it and
  `flow.py` must not declare one. Re-adding `declare_vector_index()` would
  silently bring one back on the next ingestion;
  `tests/test_search_chunks.py::test_no_ann_index_on_embedding` guards it.
- **No delete path exists** (review finding 4). Chunks were removed by
  hand twice on 2026-09-30: the `14-en` benchmark copy, and repository 14
  (full FastAPI, 22,333 chunks, indexed before the cap and exclusions and
  otherwise still `ready` and serving 75%-strict retrieval). For 14 the
  Core API row was also set to `failed` by hand — a write into another
  service's table (decision 021). CocoIndex's per-App state for
  `repoviva-14` still records rows that no longer exist, so re-ingesting
  that id would need its state reset too.
- The translation list is explicit language codes; a repository using a
  code not in the list, or another layout (e.g. `locales/`), still gets
  its translations indexed.

**Revisit when:**
- Users routinely hit the cap on repositories the product should serve —
  that is the signal to adopt HNSW (alternative above), with a recall
  check against exact search, then partitioning if post-filtering recall
  degrades.
- Any coupled parameter above changes (hardware, embedding model or
  dimension, `top_k`, chunking, include/exclude patterns) — re-measure and
  re-derive the cap.
- **A real cold-start measurement exists** (Postgres restarted, OS page
  cache dropped, first retrieval of an interview). That is the number that
  should set the cap: if cold opening-turn latency stays well inside the
  turn budget at 7,000–10,000 chunks, raise the cap to where the *turn*
  budget breaks, not the sub-budget.
- Measured warm p95 retrieval on a real deployment exceeds 100 ms for a
  repository under the cap, or the turn-latency budget tightens.
- **Repository deletion is exposed in the API, or manual chunk cleanup
  happens a third time** — build the delete path (chunks + CocoIndex App
  state) and stop editing rows by hand.

---

## 034 — Interview questions are generated at runtime by Voice Service

**Decision:**
Voice Service generates every interview question at runtime, during the
live session. The opening question is generated at session start
(retrieval → LLM); each later question is generated after the candidate's
answer, from retrieval over that answer plus the conversation so far. No
question plan or question bank is produced ahead of time. Repository
Service does not generate questions — it ingests and retrieves only
(decision 023).

**Why:**
- Two requirements depend on the candidate's live answer — "System can
  ask relevant follow-up questions" and "Interview maintains conversation
  context" — so runtime generation is required regardless of how main
  questions are chosen.
- No requirement asks for guaranteed coverage of the repository, which is
  the main thing a pre-built question plan would provide. Adding a planner
  now would be machinery without a requirement behind it.
- Generating questions is interview logic, not repository knowledge, so it
  belongs in Voice Service, which owns the live session.

**Alternatives considered:**
- **Pre-generate questions at ingestion time (Repository Service).**
  Rejected: puts interview logic in the wrong service (decision 023), and
  every interview on the same repository would get the same questions,
  undermining repeat practice (decision 002).
- **Hybrid — per-interview topic plan at session start, questions phrased
  at runtime.** Deferred, not rejected. Mirrors how a human interviewer
  works and would guarantee coverage, but adds stored plan state. Adopt if
  the revisit triggers below fire.

**Tradeoff:**
- The opening turn is the slowest turn: it waits on retrieval and a full
  LLM call before any audio plays, and its retrieval is the one most
  likely to hit uncached rows (decision 033).
- Without a plan, questions may concentrate on a narrow part of the
  repository or repeat within an interview.

**Consequences:**
- Turn will record the IDs of the chunks retrieved for each question, so
  coverage and repetition can be measured, and so `exclude_chunk_ids`
  (decision 032) can steer retrieval away from already-used code. *To be
  confirmed when the Turn schema is designed.*
- Per-turn timing must be logged by stage (retrieval, LLM, TTS), including
  the opening turn, or the first revisit trigger cannot be checked.

**Revisit when:**
1. Opening-turn latency exceeds the 4–5 s p95 turn target (decision 006),
   as measured by per-turn timing logs.
2. Interviews concentrate on a narrow set of files, measured as distinct
   files cited across an interview's questions.
3. Questions repeat within an interview despite chunk exclusion.
---

## 035 — Interview session tokens: opaque, single-use, hashed, consumed via Core API

**Decision:**
`POST /v1/interviews` issues a session token that Voice Service exchanges
with Core API once, when the interview WebSocket starts.

- **Format:** opaque random value, `secrets.token_urlsafe(32)`. No
  structure, no claims — Voice Service never parses it.
- **Lifecycle:** single-use; expires 5 minutes after issue if unused. One
  token per interview. A dropped connection is not resumed (decision
  008); the user receives a partial report and may start a new interview.
- **Storage:** Core API stores only a SHA-256 hash of the token, in three
  columns on `interviews`: `session_token_hash` (unique),
  `session_token_expires_at`, `session_token_consumed_at`. The raw token
  is returned once, in the `POST /v1/interviews` response, and never
  stored.
- **Transport to Voice:** the client sends the token inside the first
  WebSocket message (`session.start`) — not in the URL query string,
  which is commonly logged. Browsers' WebSocket API cannot set custom
  headers, so an `Authorization` header is not an option.
- **Consumption:** Voice Service calls Core API:

      POST /internal/v1/session-tokens/consume      (HMAC-signed, decision 027)
      body: { token: string }
      → 200 OK  { interview_id, user_id, repository_id }
      → 403 Forbidden { reason: "unknown" | "expired" | "consumed" }
      → 401 Unauthorized (missing or invalid HMAC signature)
      → 422 Unprocessable Entity (malformed body)

  Core API hashes the token and consumes it in one conditional
  `UPDATE … SET session_token_consumed_at = now() WHERE
  session_token_hash = $1 AND session_token_consumed_at IS NULL AND
  session_token_expires_at > now() RETURNING …`. If no row is returned, a
  follow-up read decides the `reason`.
- **Client-facing failure:** on any 403, Voice Service closes the
  WebSocket with code 1008 (Policy Violation, RFC 6455) and one generic
  message. The specific `reason` is logged by Voice, not shown to the
  client.

**Why:**
- **Single-use is the deciding property.** A stored token can be marked
  consumed in the same statement that validates it, so a replayed or
  leaked token fails. A signed self-contained token (option B) cannot be
  single-use without the server recording used tokens — reintroducing
  exactly the state B was meant to avoid.
- **Core API stays the authority** over interviews and session admission,
  consistent with decision 021: Voice never reads Core API's tables, and
  learns `interview_id`, `user_id`, `repository_id` from the consume
  response rather than from claims it must trust.
- **The network cost is off the turn path.** Consumption happens once per
  session, at connect; turns never call Core API (decision 006's budget
  is unaffected).
- **SHA-256, not bcrypt:** the token has 256 bits of randomness, so a fast
  hash cannot be brute-forced. A deterministic hash also allows lookup
  by hash; a salted slow hash would not.
- **Race-free by construction:** two simultaneous consume attempts cannot
  both match `consumed_at IS NULL`; the database guarantees only one
  succeeds.

**Alternatives considered:**
- **Signed self-contained token (HMAC/JWT).** No Core API hop at connect,
  but cannot be single-use or revoked before expiry without server-side
  state. Rejected.
- **Reuse the Core API session cookie on the WebSocket.** Requires both
  services on one site, couples them through the cookie, and exposes the
  WebSocket to cross-site WebSocket hijacking. Rejected.
- **Separate tokens table.** Supports many tokens per interview, which only
  matters with reconnect/resumption — out of scope (decision 008).
  Rejected for now.

**Tradeoff:**
- Voice Service cannot admit a session while Core API is down. Accepted:
  admission is an authentication boundary, and the cost is paid once per
  interview.
- A network blip ends the interview; the user must start a new one.
- Revoking a token affects only connections not yet made — an active
  session is not cut off. Acceptable because sessions are short and
  single-use tokens cannot be reused afterwards.
- Distinct 403 reasons give a caller holding the HMAC secret a way to
  learn whether a token exists. Acceptable: only internal services hold
  the secret, and clients only ever see the generic close.

**HMAC note (decision 027 revisit trigger):**
Voice Service is the third internal caller, which is decision 027's
revisit trigger. Decision: keep one shared secret for now — all services
run in one trust boundary on one Docker network, and per-caller identity
would not change any authorization decision we currently make. Revisit
when services are deployed across separate networks or hosts, or when an
endpoint should accept some internal callers but not others.

**Consequences:**
- Voice Service closes any connection that does not send `session.start`
  within a short timeout (recommendation: 10 s), so unauthenticated
  sockets cannot sit open.
- `architecture.md` must be updated: interviews columns, the new internal
  endpoint, and the `session.start` token transport.

**Note — implementation details (consume endpoint):**
Four points settled while building `consume_session_token`, none of
which change the contract above:
- **The `UPDATE` also requires `status = 'created'`.** That makes the
  consume statement the only way into `active` (decision 036) and stops
  a token from reviving an interview that has already ended.
- **The rejection reason is checked in the order `unknown` → `consumed` →
  `expired`.** Both columns only ever move one way, and a token can't be
  consumed after it expires. Checking `consumed` first therefore stays
  correct even when another request won the race a moment earlier. The
  classifying read runs in the same transaction as the `UPDATE`, so both
  use the same `now()`. The only other way for the `UPDATE` to miss is an
  unused, unexpired token whose interview isn't `created`, which the
  invariants rule out. If it happens anyway, the service logs an error
  and answers `unknown`.
- **Commit before responding 200.** The token is burned as soon as Core
  API says yes. If anything fails after the commit, the interview is
  left stuck in `active`, the risk decision 036 already accepts. The
  token still can never be used twice.
- **The 403 body is exactly `{ "reason": ... }`.** The endpoint returns a
  `JSONResponse` because an `HTTPException` would wrap it as `{ "detail": ... }`.
  `token` is capped at 128 characters (the current format is 43), so a
  caller can't make Core API hash arbitrarily large input.

**Revisit when:**
- Live session resumption is adopted (decision 008) — tokens would need
  to allow reconnection, likely via a separate tokens table.
- Users fail to connect within 5 minutes in practice — tune expiry.
- Core API availability at connect time becomes a measured problem.

---

## 036 — Interview lifecycle: four states, end-of-session reported via event callback

**Decision:**
Core API owns the `interviews` table and its `status`. States:

    created ──(token consumed)──▶ active ──▶ completed
                                     └─────▶ interrupted

- `created` — written by `POST /v1/interviews`.
- `active` — written by `POST /internal/v1/session-tokens/consume`, in the
  same `UPDATE` that consumes the token (decision 035). The consume time
  doubles as the session start time; there is no separate `started_at`.
- `completed` / `interrupted` — terminal. Written by Core API on receiving
  an event from Voice Service. `interrupted` covers every early ending
  (disconnect, provider error, crash detected by Voice); `error_message`
  is set when an error caused it. Both lead to a report — full or partial
  (decision 008).

Strict transitions: only `created → active` and `active → completed |
interrupted`. Any other transition is rejected with 422.

Table:

    interviews
      id                         PK
      owner_user_id              FK users.id, ON DELETE CASCADE, indexed
      repository_id              FK repositories.id, indexed
      status                     String(32) + StrEnum (as repositories)
      error_message              nullable
      session_token_hash         unique
      session_token_expires_at
      session_token_consumed_at  nullable
      created_at, updated_at
      ended_at                   nullable

Voice Service reports the end of a session the same way Repository
Service reports ingestion (decision 029):

    POST /internal/v1/interviews/{interview_id}/events   (HMAC-signed)
    body: {
      event_id:    <uuid v4>,
      event_type:  "interview.completed" | "interview.interrupted",
      occurred_at: <ISO 8601, UTC>,
      data:        { error_message?: string }
    }
    → 202 Accepted   → 401 bad signature
    → 404 unknown interview   → 422 illegal transition

No retry, no `event_id` deduplication — as in decision 029.

**Why:**
- Every stored state has a writer. States without one were dropped:
  `expired` (nothing runs at expiry time — derived instead: a `created`
  interview past `session_token_expires_at`), and `cancelled` (no
  requirement asks for it).
- `failed` was replaced by `interrupted`: under decision 008, an early
  ending produces a partial report whatever caused it, so "finished vs.
  ended early" is the distinction that matters downstream.
- Strict rather than loose transitions (unlike decision 029): there are
  only two events per interview, `active` is set inside Core API itself,
  so the out-of-order race that motivated the loose ingestion machine
  cannot occur here.
- Reusing decision 029's event envelope gives the codebase one pattern
  for "service reports a state change to its owner", and keeps `event_id`
  in the wire format so dedup can be added later without changing senders.

**Tradeoff:**
- **Stuck `active` interviews.** If Voice Service crashes or restarts
  mid-session, no end event is sent — and retries would not help, since
  the sender is gone. The interview stays `active` and receives no
  report. This will happen routinely during development (every Voice
  restart). Accepted because no data is lost: turns are persisted as they
  complete (decision 008), so a stuck interview can be ended and reported
  on later.
- A dropped event (rare, same network) has the same effect.

**Revisit when:**
- Stuck `active` interviews appear outside development, or a user misses
  a report because of one. Likely fix: Core API treats an `active`
  interview older than a maximum interview length as `interrupted`
  (lazily on read, or via a periodic sweep) and triggers its report.
- Voice Service is deployed in a way that restarts it during user
  sessions (rolling deploys, autoscaling).
- Dedup becomes necessary per decision 029's triggers.
---

## 037 — Core API's Alembic manages only Core API's tables

**Decision:**
`core-api/migrations/env.py` passes an `include_object` hook to both
`context.configure()` calls (offline and online). The hook excludes any
table that exists in the database but has no Core API model
(`type_ == "table" and reflected and compare_to is None`), so
autogenerate never proposes creating, altering, or dropping another
service's tables.

**Why:**
Generating the interviews migration (decision 036), autogenerate emitted
`op.drop_table('code_chunks')` alongside the new table. Autogenerate
compares the live database against `Base.metadata`, which only knows Core
API's models. `code_chunks` is owned by Repository Service (decision 031)
but lives in the same database and the same `public` schema, so to
Alembic it looked like a table whose model had been deleted. Applying
that migration would have dropped every chunk and embedding of every
ingested repository. It was caught only by reading the generated file
before applying it.

Decision 021's ownership rule ("no service reads or writes another
service's tables") was followed by Core API's application code but not
by its migration tooling. Deleting the line by hand would fix one
migration; every future autogenerate would propose it again. The hook
encodes the ownership rule where the tooling can enforce it.

**Alternatives considered:**
- **Delete the line by hand in each migration.** Rejected: relies on a
  human catching it every time; one miss destroys another service's data.
- **Allowlist Core API's tables by name in the hook.** Explicit, but must
  be updated for every new table — forgetting would silently skip a new
  Core API table from autogenerate. Rejected in favour of deriving
  ownership from the models themselves.
- **Move Repository Service into its own Postgres schema** (the
  per-service-schema model stated in `architecture.md`), and scope Core
  API's autogenerate to its schema. The structural fix, but a larger
  change touching Repository Service's DDL and queries (decision 031's
  revisit item). Deferred.

**Tradeoff:**
- If Core API intentionally removes one of its own models, autogenerate
  will no longer emit the `drop_table` — it must be written by hand.
  Accepted: a missing drop is harmless and visible; a wrong drop
  destroys data.
- The hook protects only against autogenerate. A hand-written migration
  can still touch another service's tables; that remains a review rule,
  not an enforced one.

**Note — unrelated drift found at the same time:**
Autogenerate also proposed dropping `ix_users_github_user_id`. The users
migration created both an unnamed unique constraint and a redundant
unique index on `github_user_id`; the model now declares only the
constraint. Uniqueness is unaffected either way. Deliberately left out of
the interviews migration (one migration, one change) and deferred to its
own cleanup migration alongside the naming-convention item in
`architecture.md`.

**Revisit when:**
- Repository Service moves `code_chunks` into its own Postgres schema
  (decision 031's revisit trigger) — Core API's autogenerate can then be
  scoped by schema, and this hook becomes redundant.
- Another service adopts Alembic against the same database — it needs the
  same hook, or the same incident repeats in the other direction.

---

## 038 — LLM provider for question generation: Groq

**Decision:**
Voice Service generates interview questions with Groq's
`llama-3.3-70b-versatile`, called through `litellm` (model string
`groq/llama-3.3-70b-versatile`). The model name lives in config
(`LLM_MODEL`), so it can change without a code change.

**Why:**
- **Cost:** Groq's free tier covers development and demos with no spend.
- **Latency:** Groq serves open models with very high throughput. A short
  question finishes in well under a second, which leaves room in the
  4–5 s turn budget (decision 006) for retrieval and, later, STT and TTS.
- **Portability:** `litellm` is already a Repository Service dependency.
  Going through it keeps the provider a config value, not an SDK baked
  into the session code.

**Alternatives considered:**
- **Claude or OpenAI models:** stronger question quality, but paid from
  the first request. They stay one config change away.
- **A local model (Ollama):** free and private, but too slow on
  development hardware for the turn budget.

**Tradeoff:**
- Free-tier rate limits (requests and tokens per minute and per day) can
  reject requests during heavy testing. Each interview makes roughly one
  LLM call per question, so ~10 concurrent interviews is within range,
  but long prompts that carry many chunks eat the token allowance quickly.
- An open 70B model may phrase questions less sharply than a frontier
  model. That's acceptable while the loop itself is being built.

**Revisit when:**
- Rate-limit errors show up in normal use (not just load tests).
- Question quality, judged on real interviews, is the weakest part of
  the product.
- The deployment moves past free-tier usage.

---

## 039 — First Voice Service slice is text-only; WebSocket protocol v1

**Decision:**
The first Voice Service slice runs the whole interview loop with text in
and text out. The client sends its answer as text (`answer.text`), and
the server sends questions as text (`question.text`). STT and TTS are
added in the next slice, behind the same loop, once those providers are
chosen.

Protocol v1 (JSON text frames, each `{ "type": ..., ...fields }`):

    Client → Server
      session.start  { token }
      answer.text    { text }        // stand-in for audio.chunk/audio.end
      session.end    {}

    Server → Client
      session.ready  { interview_id }
      question.text  { turn_id, seq, text }
      turn.complete  { turn_id }
      session.end    { reason: "completed" | "ended_by_client" }
      error          { code, message }

Endpoint: `/v1/ws/interview` on Voice Service. The token travels only in
`session.start` (decision 035). A socket that doesn't send
`session.start` within 10 s, or whose token is rejected, is closed with
code 1008.

**Why:**
- The parts that make RepoViva different are retrieval, grounding and
  prompting (decision 013). A text loop lets them be built, tested and
  tuned without audio plumbing and without paying for STT or TTS.
- Decision 003 (voice-only) still applies to the product. Text mode is a
  development stage, not a user-facing modality.
- Every message except `answer.text` is final, so the frontend and the
  audio slice build on this protocol instead of replacing it.

**Tradeoff:**
- Text answers are cleaner than transcripts. Prompts tuned on typed
  answers may need adjusting for STT output (filler words, misheard
  identifiers).
- Latency measured in this slice leaves out STT and TTS, so it
  understates the real turn time.

**Revisit when:**
- The audio slice starts: `answer.text` is then replaced by `audio.chunk`
  and `audio.end`, and `question.audio_chunk` is added.
- Accessibility needs a permanent text fallback (decision 003's revisit
  trigger).

---

## 040 — `turns` table, owned by Voice Service

**Decision:**
Voice Service owns a `turns` table (decision 010's single-Turn shape). Its
DDL lives in `voice-service/sql/schema.sql` and is applied idempotently
at startup, the same way as Repository Service (decision 031).

    turns
      id                   BIGSERIAL PK
      interview_id         BIGINT NOT NULL, indexed   -- no FK
      seq                  INT NOT NULL               -- 1-based within interview
      question_text        TEXT NOT NULL
      retrieved_chunk_ids  BIGINT[] NOT NULL
      answer_text          TEXT NULL
      status               TEXT NOT NULL              -- 'asked' | 'answered'
      timings              JSONB NOT NULL             -- per-stage ms
      created_at           TIMESTAMPTZ DEFAULT now()
      answered_at          TIMESTAMPTZ NULL
      UNIQUE (interview_id, seq)

A turn is inserted as `asked` when its question is sent, and updated to
`answered` when the answer arrives.

**Why:**
- **No foreign key to `interviews`:** decision 021 says no service touches
  another's tables. An FK would make Voice Service's schema depend on Core
  API's migrations and table names. Integrity comes from the fact that
  Voice Service only learns an `interview_id` from a successful token
  consume.
- **`retrieved_chunk_ids`** makes coverage and repetition measurable and
  feeds `exclude_chunk_ids` (decision 034's consequence).
- **`timings`** covers decision 034's per-stage timing requirement
  without a separate metrics table.
- **Persisting the question before the answer** means an interrupted
  interview still records what was asked. That's the material for the
  partial report (decision 008).

**Tradeoff:**
- Deleting an interview won't cascade to its turns. That belongs to the
  cross-service deletion flow already listed under Future Evolution in
  `architecture.md`.
- The table sits in `public` alongside `code_chunks`. Core API's Alembic
  ignores it because of decision 037's hook.

**Revisit when:**
- Questions and answers get separate lifecycles (decision 010).
- The per-service-schema split happens (decision 031).

---

## 041 — How an interview ends

**Decision:**
An interview ends in one of three ways:
1. **Question budget reached.** After the answer to question N
   (`MAX_QUESTIONS`, default 6), Voice Service sends
   `interview.completed` to Core API.
2. **The client sends `session.end`.** This also counts as
   `interview.completed`, because the user chose to stop.
3. **The socket drops or the session fails** (provider error, crash
   caught in the runner). Voice Service sends `interview.interrupted`
   with an `error_message`.

The end event goes to Core API's `POST /internal/v1/interviews/{id}/events`
(decision 036).

**Why:**
- A fixed budget keeps sessions short and predictable, both for users and
  for the free-tier LLM allowance (decision 038).
- A user who stops on purpose has finished their interview. Calling it
  "interrupted" would mislabel it, and both outcomes get a report anyway
  (decision 008).
- Whether a turn was answered is already recorded in `turns.status`, so
  the event doesn't need to carry it.

**Tradeoff:**
- A fixed count ignores how well the interview is going. An adaptive
  ending (stop once coverage is good enough) is deferred.
- A Voice Service crash still leaves the interview stuck in `active`,
  as decision 036 already accepts.

**Revisit when:**
- Users find 6 questions too few or too many.
- A topic plan (decision 034's hybrid option) makes coverage-based
  endings possible.

---

## 042 — Retrieval queries for opening and follow-up questions

**Decision:**
- **Opening question:** retrieve with a fixed seed query: "application
  entry point, core architecture, main modules and how they connect".
- **Later questions:** query with the previous question plus the
  candidate's answer.
- **Every retrieval** passes `exclude_chunk_ids` set to all chunk IDs
  already used in the interview (from `turns.retrieved_chunk_ids`), with
  `top_k = 6`.

**Why:**
- Before the candidate says anything there's no query text. A seed
  aimed at architecture gives the opening question about the most
  central code, which is also how a human interviewer starts.
- Querying with the question plus the answer keeps the follow-up
  grounded in what the candidate actually talked about. That's the
  "relevant follow-up" requirement.
- Excluding used chunks is decision 034's tool against repeated
  questions, now applied.
- `top_k = 6` keeps the prompt small for the free-tier token allowance
  (decision 038) while giving the model enough context.

**Tradeoff:**
- Every interview on the same repository opens about the same code.
  Decision 002 (repeat practice) argues for variety. A cheap later fix is
  to rotate between several seed queries.
- Exclusion can push later questions toward less central code. That's
  acceptable within a 6-question budget.

**Revisit when:**
- Users repeating interviews notice the same opening question.
- Decision 034's coverage triggers fire.

---

## 043 — Speech-to-text: Groq Whisper, batch, one call per answer

**Decision:**
Voice Service transcribes each answer with Groq's
`whisper-large-v3-turbo`, called through `litellm.atranscription` (model
string in `STT_MODEL`). The client streams raw audio while the candidate
speaks; Voice Service buffers it in memory and makes one transcription
call when the client sends `audio.end`. The question just asked is passed
as Whisper's `prompt`, so identifiers it mentions (`TurnStore`,
`pgvector`) are more likely to be spelled correctly in the transcript.

Answers are capped at `MAX_ANSWER_SECONDS` (default 180). Empty audio or
a blank transcript is reported to the client as `no_speech` and the same
turn waits for another attempt; nothing is recorded.

**Why:**
- **Same key, same library.** Groq is already the LLM provider (decision
  038). The free tier allows 2,000 transcription requests a day, which is
  hundreds of interviews.
- **Batch is enough for this product.** The next question can't be
  generated until the answer is complete anyway, so a streaming
  transcript would only buy live captions, not a faster turn. Whisper on
  Groq transcribes a minute of audio in well under a second.
- **Prompting with the question** is Whisper's documented way to bias
  vocabulary. Code interviews are dense with identifiers that general
  speech models mishear.

**Alternatives considered:**
- **Deepgram Nova-3 streaming.** Gives live partial transcripts and
  end-of-speech detection, but adds a second streaming connection per
  turn. Deferred: see revisit triggers.
- **Local Whisper.** Free and private, but too slow on development
  hardware for the turn budget (decision 006).

**Tradeoff:**
- The whole STT call sits on the turn's critical path after the
  candidate stops speaking. Measured as `stt_ms` in `turns.timings`.
- The candidate decides when the answer ends (the client sends
  `audio.end`). There is no server-side voice activity detection.
- Audio is held in memory for one answer at most, then discarded
  (decision 009).

**Revisit when:**
- `stt_ms` takes a large share of the 4–5 s budget at p95.
- The frontend wants live captions or automatic end-of-speech detection.
- Rate limits are hit in normal use.

---

## 044 — Text-to-speech: Deepgram Aura-2, streamed as raw PCM

**Decision:**
Voice Service speaks each question with Deepgram Aura-2 (voice in
`TTS_VOICE`, default `aura-2-thalia-en`) through its REST endpoint
`POST /v1/speak`, requesting `linear16` at 24 kHz with no container. The
HTTP response is read as a stream and every chunk is forwarded to the
client as a binary WebSocket frame as soon as it arrives.

**Why:**
- **Time to first audio is what the user feels.** Decision 006 measures
  latency to the moment question audio *starts*. Forwarding chunks as
  they arrive means playback can begin before synthesis finishes.
- **Raw PCM** needs no decoding on either side and can be played chunk by
  chunk; a WAV or MP3 container would have to be parsed first.
- **Cost.** About $0.03 per 1,000 characters against a $200 starting
  credit. A six-question interview is roughly 1,500 characters.
- Groq's own TTS free tier (about 100 requests a day) covers only a
  handful of interviews.

**Alternatives considered:**
- **Groq Orpheus TTS.** One provider for everything, but the free tier is
  too small to develop against.
- **Local TTS (Piper).** Free, but a weaker voice and CPU load inside the
  service.
- **Deepgram's WebSocket TTS.** Lower overhead per request, but only
  worthwhile when text arrives incrementally (streaming LLM output).

**Tradeoff:**
- A second paid vendor and API key.
- A TTS failure ends the interview as `interrupted`, the same as an LLM
  failure (decision 041). The question text was already sent, so a
  fallback to text-only was possible but would break decision 003.

**Revisit when:**
- The LLM response is streamed; TTS could then start on the first
  sentence (WebSocket TTS).
- The credit runs low or per-character cost matters.

---

## 045 — WebSocket protocol v2: audio frames

**Decision:**
Protocol v1 (decision 039) gains audio. Binary WebSocket frames carry
audio in both directions; JSON text frames carry everything else.

    Client → Server
      <binary>       answer audio: PCM16 little-endian, 16 kHz, mono
      audio.end      {}            answer finished, transcribe it
      answer.text    { text }      kept as a typed fallback
      (session.start, session.end unchanged)

    Server → Client
      question.text       { turn_id, seq, text }   sent first, as captions
      <binary>            question audio: PCM16 little-endian, 24 kHz, mono
      question.audio_end  { turn_id }
      transcript.final    { turn_id, text }
      (session.ready, turn.complete, session.end, error unchanged)

New error codes: `no_speech` and `answer_too_long` (socket stays open, the
turn waits for another answer).

The client opens the microphone only after `question.audio_end`. There
is no barge-in.

**Why:**
- **Binary frames** avoid base64 (a third larger, and an encode/decode on
  every chunk). The frame type alone tells text from audio, so no
  `audio.chunk` envelope is needed.
- **Raw PCM from the client** is what a browser `AudioWorklet` produces
  directly. The server adds the WAV header before calling STT.
- **`answer.text` stays** because it is free to keep: the runner tests,
  the CLI's typed mode and a future accessibility fallback (decision
  003's revisit trigger) all use it. It is a development path, not a
  product modality.

**Tradeoff:**
- 16 kHz PCM is about 32 KB per second, so a three-minute answer is
  about 6 MB on the socket. Fine for one user on a normal connection; a
  compressed codec (Opus) would cut it tenfold.
- Without barge-in, a candidate can't interrupt a long question.

**Revisit when:**
- Upload size matters (mobile networks): switch the client to Opus.
- Users want to interrupt questions: add barge-in.


---

## 046 — Question model: Qwen3.8 27B on Groq (Llama 3.3 retired)

**Decision:**
`LLM_MODEL` changes from `groq/llama-3.3-70b-versatile` to
`groq/qwen/qwen3.8-27b`. The provider (Groq) and the call path (litellm)
from decision 038 are unchanged; this amends only the model.

**Why:**
- Groq retired `llama-3.3-70b-versatile`. The first live audio-slice run
  failed at question generation with `model_not_found`, and the model no
  longer appears in Groq's model list.
- Of the chat models still on Groq, the candidates were compared on the
  real interviewer prompt with code retrieved from an indexed repository:

  | Model | Time | Result |
  |---|---|---|
  | `openai/gpt-oss-120b`, `max_tokens=200` | 2.1 s | empty: reasoning used the whole budget |
  | `openai/gpt-oss-120b`, `max_tokens=1000` | 1.8 s | good question, ~340 tokens |
  | `openai/gpt-oss-20b`, low effort | 1.5 s | acceptable |
  | `qwen/qwen3.8-27b` | ~0.5 s | specific, code-grounded questions, ~45 tokens |

- Qwen was the fastest by a wide margin and gave the best-grounded
  questions. That speed matters more now that TTS and STT share the 4–5 s
  turn budget (decision 006). It also works within the existing
  `max_tokens=200`.

**Tradeoff:**
- A model chosen from one comparison on one repository. Question quality
  should be judged again on real interviews.
- Groq can retire this model too. The name lives in config, so a
  replacement is a one-line change, but there is no automatic fallback.

**Revisit when:**
- Groq retires this model, or a call fails with `model_not_found`.
- Questions from real interviews are judged too long to listen to or
  poorly grounded.


---

## 047 — Compress answer audio to MP3 before STT

**Decision:**
Before the transcription call, Voice Service compresses the buffered
answer from raw PCM16 to a low-bitrate MP3 (`soundfile`/libsndfile,
`compression_level=0.9`) and sends it as `answer.mp3`. Encoding runs in a
worker thread (`asyncio.to_thread`). The client protocol is unchanged:
clients still send raw PCM (decision 045). This amends decision 043,
which sent a WAV.

**Why:**
- The first live interview (interview 7) showed `stt_ms` of 1.7–9.7 s,
  growing with the length of the recording, not the number of words. Raw
  PCM is 32 KB per second, so a three-minute answer is about 6 MB, and
  uploading it from a home connection dominated the STT time.
- Measured on a 94 s answer, sending the same audio to Groq in each format:

  | Format | Size | Encode | STT | Total |
  |---|---|---|---|---|
  | WAV (before) | 3.02 MB | 0 | ~10 s | ~10 s |
  | FLAC | 1.55 MB | 0.1 s | 4.6 s | 4.7 s |
  | Opus (OGG) | 0.30 MB | 1.8 s | 1.35 s | 3.2 s |
  | MP3, level 0.9 | 0.33 MB | 0.4–0.5 s | 1.2 s | ~1.7 s |

  Every compressed transcript matched the WAV transcript (99.6% word
  similarity), so the lossy codecs cost no accuracy at this bitrate.
- MP3 gives almost Opus's size at a quarter of the encode time. Upload
  size, not codec, decided the STT time: MP3 and Opus were within 0.1 s.
- **Worker thread:** encoding is CPU work. On the event loop it would
  pause every other interview served by the process for ~0.5 s; in a
  thread the loop keeps serving them.

**Alternatives considered:**
- **Compress on the client** (Opus from a browser `MediaRecorder`). Would
  also shrink the client → Voice upload, but changes protocol v2 and
  needs a decoder for VAD/inspection later. Revisit with the frontend.
- **Streaming STT.** Uploads while the candidate speaks, so the wait no
  longer depends on answer length at all. Larger change; still decision
  043's revisit path.
- **Encode incrementally as frames arrive.** Hides the encode time
  entirely but adds per-session encoder state. Not worth it at ~0.5 s.

**Tradeoff:**
- A native dependency (`soundfile` bundles libsndfile in its wheels).
- `stt_ms` now includes the encode time; the encode is logged separately.
- Vorbis encoding crashed the process during testing (libsndfile). Not
  used; noted in case a codec change is considered.

**Revisit when:**
- The frontend exists: compress on the client instead (see above).
- `stt_ms` still takes a large share of the turn budget: streaming STT.


---

## 048 — Scenario-based questions; code is background, not the subject

**Decision:**
The interviewer prompt (`voice-service/src/voice_service/llm/prompts.py`)
changes from code-pointed questions to scenario-based ones. Retrieved
code is still sent to the model, labelled as *background*, so questions
stay grounded in the candidate's real project (decision 013). Questions
now describe a situation the project faces in plain product and system
terms ("two customers buy the last item at once", "the payment webhook
is delayed by hours") and ask how it behaves or how the candidate would
handle it. The model is told never to name files, functions, classes or
variables.

Also changed:
- **No judgement of the previous answer** ("that was vague"). At most a
  neutral lead-in such as "Okay."
- **"I don't know" or "answer it for me"** gets a one-sentence hint and
  an easier question, or a new situation. Never the full answer, never
  the same question repeated.
- **One question per reply**, at most two sentences and 35 words. It is
  heard once and can't be re-read.
- The opening question is an easy warm-up.

**Why:**
- After interviews 7 and 8, the candidate found the questions too hard
  and too code-specific ("In the `include_object` hook, you check if
  `compare_to is None`…"). That came straight from the old prompt's rule
  "name the specific file, function, class". Recalling identifiers by
  voice tests memory of the code more than understanding of the system.
- Real interviews about your own project mostly ask how the system
  behaves in situations and why it was built that way. Scenarios test the
  same understanding without needing to remember identifiers.
- Transcripts showed the old follow-ups pressing harder after "I don't
  know" and "can you simplify" (repeating the question, "I need you to
  directly answer"), questions of 40–52 words, and two questions stacked
  in one reply.

**How it was checked:**
Interviews 7 and 8 were replayed turn by turn with the new prompt, using
the same history and the same retrieval queries. Openings and topic
changes turned into situations in 23–35 words with no identifiers, and
were grounded in real features (the repository's chatbot, its promotions
system). A first version still gave the full answer when asked to, judged
an answer, and ran long. The rules above fixed those on re-test.
Remaining imperfections: an occasional "…and…" double question, and a
"simplified" follow-up that still ran 41 words.

**Tradeoff:**
- Questions are less precise about specific code, so a candidate can
  answer well without knowing implementation details. That is accepted:
  RepoViva is practice for explaining a project.
- Instruction following is imperfect: length and one-question rules are
  usually but not always kept. Not enforced in code.
- **Rate limits found while testing:** Groq's free tier for
  `qwen/qwen3.8-27b` allows about 8,000 tokens per minute and 1,000
  requests per day. A question prompt is about 2,000 tokens, so that is
  3–4 questions per minute across all users. One interview at a time
  fits. The ~10 concurrent interviews target (architecture.md) does not, so a paid tier
  or a smaller prompt is needed before multi-user demos.

**Revisit when:**
- Candidates find questions too easy or too generic: add a difficulty
  setting (scenario-only vs scenario plus code detail).
- Replies regularly break the length or one-question rules: enforce in
  code (reject and regenerate).
- More than one interview runs at a time: the rate limit above.


---

## 049 — Evaluation Service contract: Core API triggers, Evaluation pulls over HTTP

**Decision:**
When Core API applies an `interview.completed` or `interview.interrupted`
event (decision 036), it asks Evaluation Service for a report:

    POST /internal/v1/reports                      (HMAC-signed, decision 027)
    body: { interview_id, repository_id, outcome: "completed" | "interrupted" }
    → 202 Accepted

Evaluation Service then gathers its inputs over HTTP. It never reads
another service's tables (decision 021):

    Voice Service       GET  /internal/v1/interviews/{interview_id}/turns
                        → 200 { turns: [ { seq, question_text, answer_text,
                                           status, retrieved_chunk_ids } ] }
    Repository Service  POST /internal/v1/repositories/{repository_id}/chunks
                        body: { ids: int[] }   (1–200 ids)
                        → 200 { chunks: [ same shape as /retrieve, no similarity ] }

The report is stored in Evaluation's own `reports` table, one row per
interview (`interview_id` UNIQUE). Its `status` is `generating`, `ready`
or `failed`. Core API keeps no report metadata. It serves reports to the
frontend by proxying:

    Frontend → Core API     GET /v1/interviews/{id}/report   (session cookie, owner only)
    Core API → Evaluation   GET /internal/v1/reports/{interview_id}
                            → 200 { status, partial, summary, turn_evaluations, ... }
                            → 404 no report

Core API answers 200 with the report when it is `ready` or `failed`, 202
while it is `generating`, and 404 when the interview has not ended.

Trigger rules:
- A trigger for a report that is `ready` or `generating` is a no-op.
- A trigger for a `failed` report regenerates it.
- Generation runs on FastAPI `BackgroundTasks`, like ingestion.

Two recovery paths, so a lost call delays a report but never loses it:
- **Lazy re-trigger.** If Core API's report proxy gets a 404 for an
  interview that is `completed` or `interrupted`, it sends the trigger
  again and answers 202.
- **Startup resume.** On boot, Evaluation re-schedules every report
  still in `generating`.

**Why:**
- **Core API triggers, not Voice Service.** Core API owns the interview
  lifecycle and already knows `repository_id` and the outcome when it
  applies the end event. Voice Service would have to send a second call
  at session end, the moment it is most likely to be failing.
- **HTTP, not a broker.** The rest of the system already uses
  HMAC-signed HTTP for every internal call (decisions 027, 029, 035). A
  report needs about five calls, and the work is in the background, so
  hop latency doesn't matter. A broker is infrastructure `requirements.md`
  lists as out of scope, and none of decision 029's triggers for one
  apply yet.
- **Pull, not push.** Turns and chunks are already persisted by their
  owners. Fetching them at generation time means the trigger can be
  sent again at any point and still produce the same report.
- **Chunks by id, not re-retrieval.** `turns.retrieved_chunk_ids`
  (decision 040) records the exact code each question was generated
  from. Grading against the same code is fairer than searching again.
- **No report metadata in Core API.** Evaluation already holds the
  status. Copying it into Core API would need a callback and a second
  source of truth for one field.
- **The two recovery paths** cover the weak spots of fire-and-forget
  HTTP: Evaluation down when the trigger is sent, and a crash or
  `--reload` mid-generation. Both are cheap because the `reports` row is
  written before the work starts, so the table doubles as a durable job
  list.

**Tradeoff:**
- Evaluation depends on Voice and Repository being up while it
  generates. If either is down the report is `failed`, and recovers on
  the next trigger.
- A `failed` report is served as is. It is regenerated only when a
  trigger arrives, not when it is read.
- Core API can't list interviews with their report status without one
  call per interview. Acceptable while no screen needs that list.
- An interview stuck in `active` (decision 036) gets no trigger and no
  report until it is ended.

**Revisit when:**
- Reports sit in `generating` for a long time under load, or several
  must run in parallel with controlled concurrency: move to a
  Postgres-backed job table with workers before considering a broker.
- A second service needs to react to "interview ended" (decision 029's
  second-consumer trigger).
- The frontend needs report status in interview lists.

---

## 050 — Report shape: per-turn grading on two 1–5 scores, grounded in the turn's code

**Decision:**
**Per turn.** Each answered turn is graded in its own LLM call. The call
gets the question, the answer, the previous exchange for context, and
the code chunks the question was generated from. The model returns JSON,
validated with pydantic:

    {
      correctness:        { score: 1–5, justification },
      clarity:            { score: 1–5, justification },
      strengths:          [string],
      gaps:               [string],
      key_points:         [ { point, chunk_ids: [int] } ],   // 2–4
      evidence_chunk_ids: [int]
    }

- **Correctness** means the answer is true of *this* code, not of
  software in general.
- **Clarity** means structure, precision, and whether the answer
  responds to the question that was asked.
- **Key points** are what a strong answer would have covered. They are
  the practice value of the report.

**Grounding rules, enforced in code:**
- Chunk ids not among the turn's chunks are dropped.
- A key point with no valid chunk id left is dropped.
- Chunk ids written in the prose ("as chunk 142 shows") are replaced with
  `file:line`. The prompt asks the model not to write them, but it
  doesn't always comply, and an id means nothing to the candidate.
- Invalid JSON gets one retry. After that the turn is `not_graded`, and
  the rest of the report is still produced. Groq's JSON mode sometimes
  rejects the model's malformed JSON with a 400 `json_validate_failed`;
  that counts as invalid JSON, not a provider failure.

**Summary.** One last LLM call reads the per-turn results and writes up
to 3 strengths (taken only from the per-turn strengths, so possibly
none), 2–3 areas to improve, and up to 3 files worth revisiting (only
files behind a graded turn, checked in code). The numbers are computed in
code: average correctness, average clarity, turns answered and turns
asked.

**Partial interviews (decision 008):**
- Turns still `asked` are listed as `not_answered` and left out of the
  averages.
- `partial` is true when the outcome was `interrupted`.
- With no answered turns, the report is still produced, with no scores.

Each report stores the `model` and a `prompt_version`, so scores from
different prompts are never compared by mistake.

**Why:**
- `requirements.md` names the two dimensions: technical correctness and
  explanation quality. They can disagree (a clear answer that is wrong,
  or a right answer that rambles), so they are scored separately.
- **1–5, not 0–100.** LLM judges are more consistent on small scales,
  and each score comes with a justification the candidate can check.
- **Per turn, not one call for the whole transcript.** Each call sees
  only the code that matters for that question, which keeps grading
  grounded and the prompt small. One bad response costs one turn, not
  the report.
- **Averages in code.** An LLM's arithmetic and its idea of "overall"
  drift. Code doesn't.
- **Citations checked in code.** `requirements.md` asks for evaluations
  grounded in the repository. Checking that every cited chunk was
  actually shown to the model is the cheapest guard against invented
  claims about the code.

**How it was checked:**
Two checks, both with `gpt-oss-120b` (decision 051):
- **Interview 7 report**, read by eye after each prompt change
  (`evaluation-service/scripts/eval_report.py`). Scores tracked the
  answers: "I don't know" got 1/5, and the one real explanation (the
  deadlock question) got 4/4.
- **Grader sanity set** (`evaluation-service/evals/`). Two real
  questions from interview 7, each with a strong, a vague and a wrong
  answer written from the code before any grading run.

The prompt went through five versions; each fixed something the checks
showed:

| Version | Problem found | Change |
|---|---|---|
| v1 | Prose cited "chunk 142"; a key point proposed a redesign the code doesn't have; the summary invented a strength; "I don't know" was called "incomprehensible" | v2 rules for each |
| v2 | Sanity set 15/16: a vague answer scored 4 (the model filled in the mechanism); a strong answer scored 3, marked down for claims the excerpts couldn't confirm and for suggesting a fix | Credit only what was said; unconfirmable claims and suggestions aren't errors. Chunk ids replaced in code |
| v3 | Sanity set 24/24 over 3 runs, identical scores each run. But "I don't know" turns came back with no key points | Key points always required |
| v4 | Tried "restating the question earns nothing" to push the vague answer from 3 to 2. No effect; reverted | — |
| v5 | A summary file reason claimed a file "contains the accidental commit" (it doesn't) | Reasons say what to study, never what a file contains |

Sanity set on v3 (3 runs): strong 5/5/5 and 5/5/5, vague 3/3/3 and
1/1/1, wrong 2/2/2 and 1/1/1. The wrong answers' gaps named the actual
mistake every time. The final v5 prompt changes only the key-point and
summary instructions; its sanity run is pending because the day's token
budget ran out during tuning (decision 051).

**Tradeoff:**
- About seven LLM calls per report instead of one, which is slower
  under the free-tier rate limit (decision 051).
- **Lenient on vague answers.** A vague answer that repeats the
  question's own terms scores 3, not the 2 the rubric asks for. It still
  ranks below a strong answer and above a wrong one. Two prompt rules
  didn't move it.
- The judge only sees the chunks the question was built from. An answer
  that is correct about code outside those chunks can be under-scored.
- A dropped key point is silent to the candidate. The count of dropped
  citations is logged so it can be watched.

**Revisit when:**
- Candidates often dispute correctness scores about code outside the
  turn's chunks: add a retrieval on the answer itself.
- Scores for the same answer vary a lot between runs: lower the
  temperature, or grade twice and average.
- A third dimension is asked for (for example depth, or tradeoff
  awareness).

---

## 051 — Evaluation model: GPT-OSS 120B on Groq, separate from the question model

**Decision:**
Evaluation Service calls `groq/openai/gpt-oss-120b` through litellm, with
low reasoning effort and JSON output. The name is a config value,
`EVAL_LLM_MODEL`, separate from Voice Service's `LLM_MODEL`
(`qwen/qwen3.8-27b`, decision 046). Calls run one after another. On
HTTP 429 the service waits as long as Groq asks (the wait is in the
error message, "try again in 6.5s"; 15 s if it doesn't say), up to 8
times. A wait over 60 s means the daily limit is spent, so the report
fails at once and a later trigger regenerates it (decision 049).

**Why:**
- **A separate model is a separate rate-limit bucket.** Groq's free tier
  gives each chat model about 8,000 tokens per minute and 1,000 requests
  per day (all three candidates checked through response headers on
  2026-10-08). Grading on the question model would take tokens from
  live interviews, where latency matters (decision 006).
- **A stronger judge than the question model.** Grading has to check an
  answer against code and explain its reasoning. That is harder than
  writing a 35-word question, and speed doesn't matter in the
  background.
- Of the chat models on Groq (`gpt-oss-120b`, `gpt-oss-20b`,
  `qwen3.8-27b`, `allam-2-7b`), the 120B model is the largest. It has a
  131k context window and supports JSON output.

**Measured (2026-10-08):**
- A six-turn report (interview 7) took 58–90 s. After the first two
  calls, each call waited once for the per-minute limit (~15 s).
- **Daily limit: 200,000 tokens per model**, found when tuning hit it.
  It's in the 429 message, not the response headers checked earlier. A
  grading call requests about 2.7k tokens, so a six-turn report is
  roughly 18k: **about 10 reports a day** on the free tier. Each report
  now logs its token count, so this can be measured rather than
  estimated.
- Grading quality: decision 050's sanity set, 24/24 checks over 3 runs.

**Tradeoff:**
- About 10 reports a day across all users. Enough for development and a
  demo; not for real use.
- A daily-limit 429 fails the report instead of waiting hours. It is
  regenerated on the next trigger, including the lazy re-trigger when
  the report is read (decision 049).
- Same single-provider risk as decision 046: Groq can retire the model.
  The name is in config.

**Revisit when:**
- The sanity set doesn't rank strong > vague > wrong on correctness.
- Reports fail on the daily limit outside development, or more than
  about 10 interviews a day are expected: a paid tier, `gpt-oss-20b`
  (its own 200k bucket, but check the sanity set first), or a shorter
  prompt.
- Groq retires the model.
