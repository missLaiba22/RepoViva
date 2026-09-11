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