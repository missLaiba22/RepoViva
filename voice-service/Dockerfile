# Build from the repo root: docker build -f voice-service/Dockerfile .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY libs/repoviva-common /app/libs/repoviva-common
WORKDIR /app/voice-service

COPY voice-service/pyproject.toml voice-service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY voice-service ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/voice-service/.venv/bin:$PATH"

EXPOSE 8002
# The worker uses the same image: `python -m voice_service.worker`.
CMD ["uvicorn", "voice_service.main:app", "--host", "0.0.0.0", "--port", "8002"]
