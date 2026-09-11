from fastapi import FastAPI

from repository_service.internal.router import router as internal_router

app = FastAPI(
    title="RepoViva Repository Service",
    description="Owns repository ingestion and retrieval.",
    version="0.1.0",
)

app.include_router(internal_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies.
    Kept trivial on purpose — this endpoint exists so docker-compose,
    integration tests, and (later) load balancers can check the process
    is up without needing to know anything about the service's state.
    """
    return {"status": "ok"}