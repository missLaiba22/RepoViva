from fastapi import FastAPI

app = FastAPI(
    title="RepoViva Repository Service",
    description="Owns repository ingestion and retrieval.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe. No auth, no dependencies.
    Kept trivial on purpose — this endpoint exists so docker-compose,
    integration tests, and (later) load balancers can check the process
    is up without needing to know anything about the service's state.
    """
    return {"status": "ok"}