#!/usr/bin/env python3
"""Write the four services' .env.prod files from one secrets file (decision 063).

On the server: fill in ~/repoviva-secrets.env (template: secrets.env.example), then
    python3 ~/RepoViva/infra/aws/make_env.py
Prints only key names, never values.
"""
import base64
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REPO = Path(__file__).resolve().parents[2]
SECRETS = Path.home() / "repoviva-secrets.env"
# Kept so reruns never rotate keys: a new TOKEN_ENCRYPTION_KEY would make stored
# GitHub tokens unreadable.
GENERATED = Path.home() / "repoviva-generated.env"

REQUIRED = ["AWS_REGION", "AWS_ACCOUNT_ID", "DOMAIN", "NEON_URL", "MONGODB_URI",
            "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "VOYAGE_API_KEY", "GROQ_API_KEY",
            "DEEPGRAM_API_KEY"]
PLACEHOLDERS = ("<paste>", "<db_password>")


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def pg_urls(neon: str) -> tuple[str, str]:
    """Core API's psycopg URL and the asyncpg URL; asyncpg rejects channel_binding."""
    parts = urlsplit(neon)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "channel_binding"]
    if not any(k == "sslmode" for k, _ in query):
        query.append(("sslmode", "require"))
    plain = urlunsplit(("postgresql", parts.netloc, parts.path, urlencode(query), ""))
    return plain.replace("postgresql://", "postgresql+psycopg://", 1), plain


def main() -> None:
    if not SECRETS.exists():
        sys.exit(f"missing {SECRETS}: copy infra/aws/secrets.env.example there and fill it in")
    s = read_env(SECRETS)
    missing = [k for k in REQUIRED if not s.get(k) or any(p in s[k] for p in PLACEHOLDERS)]
    if missing:
        sys.exit(f"fill in: {', '.join(missing)}")
    if not re.match(r"^postgres(ql)?://", s["NEON_URL"]):
        sys.exit("NEON_URL must start with postgresql://")
    if not s["MONGODB_URI"].startswith("mongodb"):
        sys.exit("MONGODB_URI must start with mongodb+srv://")

    if not GENERATED.exists():
        GENERATED.write_text(
            f"INTERNAL_HMAC_SECRET={secrets.token_hex(32)}\n"
            f"COOKIE_SECRET={secrets.token_hex(32)}\n"
            f"TOKEN_ENCRYPTION_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}\n"
        )
        GENERATED.chmod(0o600)
    g = read_env(GENERATED)

    region, domain = s["AWS_REGION"], s["DOMAIN"]

    def queue(name: str) -> str:
        return f"https://sqs.{region}.amazonaws.com/{s['AWS_ACCOUNT_ID']}/{name}"

    core_db, async_db = pg_urls(s["NEON_URL"])
    common = {"ENV": "production", "AWS_REGION": region,
              "INTERNAL_HMAC_SECRET": g["INTERNAL_HMAC_SECRET"]}
    files = {
        "core-api": {
            **common,
            "DATABASE_URL": core_db,
            "GITHUB_CLIENT_ID": s["GITHUB_CLIENT_ID"],
            "GITHUB_CLIENT_SECRET": s["GITHUB_CLIENT_SECRET"],
            "GITHUB_OAUTH_REDIRECT_URI": f"https://{domain}/v1/auth/github/callback",
            "FRONTEND_BASE_URL": f"https://{domain}",
            "COOKIE_SECRET": g["COOKIE_SECRET"],
            "TOKEN_ENCRYPTION_KEY": g["TOKEN_ENCRYPTION_KEY"],
            "INGESTION_JOBS_QUEUE_URL": queue("ingestion-jobs"),
            "REPORT_JOBS_QUEUE_URL": queue("report-jobs"),
            "PLANNING_JOBS_QUEUE_URL": queue("planning-jobs"),
            "INTERVIEW_EVENTS_QUEUE_URL": queue("core-interview-events"),
            "INGESTION_EVENTS_QUEUE_URL": queue("core-ingestion-events"),
        },
        "repository-service": {
            **common,
            "DATABASE_URL": async_db,
            "VOYAGE_API_KEY": s["VOYAGE_API_KEY"],
            "INGESTION_JOBS_QUEUE_URL": queue("ingestion-jobs"),
            "EVENT_BUS_NAME": "repoviva",
        },
        "voice-service": {
            **common,
            "MONGODB_URI": s["MONGODB_URI"],
            "MONGODB_DATABASE": "repoviva_voice",
            "GROQ_API_KEY": s["GROQ_API_KEY"],
            "DEEPGRAM_API_KEY": s["DEEPGRAM_API_KEY"],
            "EVENT_BUS_NAME": "repoviva",
            "PLANNING_JOBS_QUEUE_URL": queue("planning-jobs"),
        },
        "evaluation-service": {
            **common,
            "DATABASE_URL": async_db,
            "GROQ_API_KEY": s["GROQ_API_KEY"],
            "INTERVIEW_EVENTS_QUEUE_URL": queue("evaluation-interview-events"),
            "REPORT_JOBS_QUEUE_URL": queue("report-jobs"),
        },
    }
    optional = {
        "voice-service": ["LLM_MODEL", "STT_MODEL", "TTS_VOICE", "MAX_QUESTIONS"],
        "evaluation-service": ["EVAL_LLM_MODEL"],
    }
    for service, keys in optional.items():
        files[service].update({k: s[k] for k in keys if s.get(k)})

    for service, values in files.items():
        path = REPO / service / ".env.prod"
        path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
        path.chmod(0o600)
        print(f"wrote {service}/.env.prod: {', '.join(values)}")


if __name__ == "__main__":
    main()
