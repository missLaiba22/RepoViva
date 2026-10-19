# Build from the repo root: docker build -f evaluation-service/Dockerfile .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY libs/repoviva-common /app/libs/repoviva-common
WORKDIR /app/evaluation-service

COPY evaluation-service/pyproject.toml evaluation-service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY evaluation-service ./
RUN uv sync --frozen --no-dev
ENV PATH="/app/evaluation-service/.venv/bin:$PATH"

EXPOSE 8003
# The worker uses the same image: `python -m evaluation_service.worker`.
CMD ["uvicorn", "evaluation_service.main:app", "--host", "0.0.0.0", "--port", "8003"]
