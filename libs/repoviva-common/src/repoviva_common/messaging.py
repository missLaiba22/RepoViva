"""SQS jobs and the worker loop (decision 057).

The only module that imports boto3. boto3 is sync: Core API calls it
directly, async services through `asyncio.to_thread`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

# A message stays hidden from other workers this long; the heartbeat keeps
# extending it while the handler runs, so long jobs don't need a huge value.
VISIBILITY_TIMEOUT_SECONDS = 60
HEARTBEAT_SECONDS = 20
WAIT_TIME_SECONDS = 20


class Message(BaseModel):
    message_id: str
    type: str
    occurred_at: datetime
    request_id: str | None = None
    data: dict[str, Any]


class MessagingError(Exception):
    """Sending a message failed."""


Handler = Callable[[Message], Awaitable[None]]

_sqs: Any = None


def open_sqs_client(
    *,
    region: str,
    endpoint_url: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
) -> None:
    """Open the process's SQS client. Keys are None on AWS (the task's IAM role)."""
    global _sqs
    _sqs = boto3.client(
        "sqs",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )


def close_sqs_client() -> None:
    global _sqs
    if _sqs is not None:
        _sqs.close()
        _sqs = None


def get_sqs_client() -> Any:
    if _sqs is None:
        raise RuntimeError("SQS client not opened — check the lifespan or worker startup")
    return _sqs


def build_message(type: str, data: dict[str, Any], *, request_id: str | None = None) -> Message:
    return Message(
        message_id=str(uuid4()),
        type=type,
        occurred_at=datetime.now(UTC),
        request_id=request_id,
        data=data,
    )


def send_job(queue_url: str, type: str, data: dict[str, Any]) -> Message:
    message = build_message(type, data)
    try:
        get_sqs_client().send_message(QueueUrl=queue_url, MessageBody=message.model_dump_json())
    except (BotoCoreError, ClientError) as exc:
        raise MessagingError(f"could not send {type}: {exc}") from exc
    return message


async def run_worker(handlers: Mapping[str, Handler], *, stop: asyncio.Event) -> None:
    """Poll each queue URL in `handlers` until `stop` is set.

    One message at a time per queue, which caps the worker's concurrency.
    A message is deleted only after its handler returns. If the handler
    raises or the process dies, it reappears after the visibility timeout,
    and after the queue's maxReceiveCount it moves to the DLQ.
    """
    await asyncio.gather(*(_poll(url, handler, stop) for url, handler in handlers.items()))


async def _poll(queue_url: str, handler: Handler, stop: asyncio.Event) -> None:
    sqs = get_sqs_client()
    while not stop.is_set():
        try:
            response = await asyncio.to_thread(
                sqs.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=WAIT_TIME_SECONDS,
                VisibilityTimeout=VISIBILITY_TIMEOUT_SECONDS,
            )
        except (BotoCoreError, ClientError):
            logger.exception("receive failed: queue=%s", queue_url)
            await asyncio.sleep(5)
            continue
        for raw in response.get("Messages", []):
            await handle_one(sqs, queue_url, raw, handler)


async def handle_one(sqs: Any, queue_url: str, raw: dict[str, Any], handler: Handler) -> bool:
    """Run `handler` on one received message. True if it was deleted."""
    receipt = raw["ReceiptHandle"]
    try:
        message = Message.model_validate_json(raw["Body"])
    except ValidationError:
        # Left on the queue: it reaches the DLQ after maxReceiveCount.
        logger.exception("malformed message: queue=%s", queue_url)
        return False

    heartbeat = asyncio.create_task(_extend_visibility(sqs, queue_url, receipt))
    try:
        await handler(message)
    except Exception:
        logger.exception(
            "handler failed, message will be redelivered: type=%s message_id=%s",
            message.type, message.message_id,
        )
        return False
    finally:
        heartbeat.cancel()

    await asyncio.to_thread(sqs.delete_message, QueueUrl=queue_url, ReceiptHandle=receipt)
    return True


async def _extend_visibility(sqs: Any, queue_url: str, receipt: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await asyncio.to_thread(
                sqs.change_message_visibility,
                QueueUrl=queue_url,
                ReceiptHandle=receipt,
                VisibilityTimeout=VISIBILITY_TIMEOUT_SECONDS,
            )
        except (BotoCoreError, ClientError):
            logger.warning("could not extend visibility", exc_info=True)

