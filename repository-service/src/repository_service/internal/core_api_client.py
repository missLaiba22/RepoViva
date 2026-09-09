# """Outbound HTTP client: fires ingestion callback events at core-api.

# Every request is HMAC-signed with the shared internal secret (see
# :mod:`repository_service.internal.hmac_auth`).
# """

# from __future__ import annotations

# import json
# import logging
# from typing import Any

# import httpx

# from repository_service.config import get_settings
# from repository_service.internal.hmac_auth import sign

# logger = logging.getLogger(__name__)

# _EVENTS_PATH = "/internal/v1/repositories/{repository_id}/events"


# class CoreApiClient:
#     def __init__(
#         self,
#         base_url: str,
#         secret: str,
#         *,
#         timeout: float = 10.0,
#         transport: httpx.BaseTransport | None = None,
#     ) -> None:
#         self._base_url = base_url.rstrip("/")
#         self._secret = secret
#         self._timeout = timeout
#         self._transport = transport  # injectable for tests

#     async def emit_event(self, repository_id: str, event: dict[str, Any]) -> None:
#         """POST a single ingestion event to core-api. Best-effort: logs on failure."""
#         body = json.dumps(event, separators=(",", ":"), sort_keys=True).encode()
#         headers = {"Content-Type": "application/json", **sign(self._secret, body)}
#         url = self._base_url + _EVENTS_PATH.format(repository_id=repository_id)

#         try:
#             async with httpx.AsyncClient(
#                 timeout=self._timeout, transport=self._transport
#             ) as client:
#                 resp = await client.post(url, content=body, headers=headers)
#                 resp.raise_for_status()
#         except httpx.HTTPError:
#             logger.exception(
#                 "failed to emit event %s for repository %s", event.get("type"), repository_id
#             )
#             raise


# def get_core_api_client() -> CoreApiClient:
#     settings = get_settings()
#     return CoreApiClient(settings.core_api_base_url, settings.internal_hmac_secret)
