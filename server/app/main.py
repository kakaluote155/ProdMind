from fastapi import FastAPI

from .investigation import investigate
from .models import InvestigationRequest, InvestigationResponse

app = FastAPI(
    title="ProdMind",
    version="0.1.0",
    description="Evidence-first AI production support engineer.",
)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "ProdMind",
        "tagline": "Software that knows why it broke.",
        "version": "0.1.0",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/investigate", response_model=InvestigationResponse)
def investigate_failure(request: InvestigationRequest) -> InvestigationResponse:
    return investigate(request)
