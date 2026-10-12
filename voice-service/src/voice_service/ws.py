"""The interview WebSocket endpoint (decision 039).

Thin: accept, wire up collaborators, hand the socket to the runner.
"""

from fastapi import APIRouter, WebSocket

from voice_service.clients.core_api import get_core_api_client
from voice_service.config import get_settings
from voice_service.db import get_db
from voice_service.session.runner import InterviewSession, SessionConfig
from voice_service.session.store import SessionStore
from voice_service.speech.stt import get_transcriber
from voice_service.speech.tts import get_synthesizer

router = APIRouter()


@router.websocket("/v1/ws/interview")
async def interview_socket(ws: WebSocket) -> None:
    # No auth before accept: the token arrives in the first message, never
    # the URL (decision 035). The runner closes the socket if it doesn't.
    await ws.accept()

    settings = get_settings()
    session = InterviewSession(
        core_api=get_core_api_client(),
        transcriber=get_transcriber(),
        synthesizer=get_synthesizer(),
        sessions=SessionStore(get_db()),
        config=SessionConfig(
            session_start_timeout_s=settings.session_start_timeout_s,
            max_answer_seconds=settings.max_answer_seconds,
        ),
    )
    await session.run(ws)
