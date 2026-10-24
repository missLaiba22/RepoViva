# repoviva-common

Infrastructure shared by the RepoViva services (decision 054). Never domain models, database code or business logic.

| Module | Provides |
|---|---|
| `hmac_auth` | `sign` / `verify` for internal HTTP calls (decision 027) |
| `dependencies` | `hmac_dependency`, a FastAPI dependency that verifies the HMAC headers |
| `http` | One long-lived `httpx` client per service, opened in the lifespan (decision 055) |
| `messaging` | `send_job`, `publish_event`, `publish_event_with_retry` and the `run_worker` loop over SQS and EventBridge (decision 057). The only module that imports `boto3` |
| `request_id` | `RequestIDMiddleware`, request-ID context and `configure_logging` (decision 056) |

Each service depends on it as a local path package, so `uv sync` in a service installs it.

## Tests

```bash
uv sync
uv run ruff check . && uv run pytest
```
