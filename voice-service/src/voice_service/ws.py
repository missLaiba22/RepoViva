"""The interview WebSocket endpoint (decision 039).

Thin: accept, wire up collaborators, hand the socket to the runner.
"""

from fastapi import APIRouter, WebSocket

from voice_service.clients.core_api import get_core_api_client
from voice_service.clients.repository import get_repository_client
from voice_service.config import get_settings
from voice_service.db import get_db_pool
from voice_service.llm.generator import get_question_generator
from voice_service.session.runner import InterviewSession, SessionConfig
from voice_service.session.turns import TurnStore

router = APIRouter()


@router.websocket("/v1/ws/interview")
async def interview_socket(ws: WebSocket) -> None:
    # No auth before accept: the token arrives in the first message, never
    # the URL (decision 035). The runner closes the socket if it doesn't.
    await ws.accept()

    settings = get_settings()
    session = InterviewSession(
        core_api=get_core_api_client(),
        retriever=get_repository_client(),
        generator=get_question_generator(),
        turns=TurnStore(get_db_pool()),
        config=SessionConfig(
            max_questions=settings.max_questions,
            session_start_timeout_s=settings.session_start_timeout_s,
            retrieval_top_k=settings.retrieval_top_k,
        ),
    )
    await session.run(ws)
