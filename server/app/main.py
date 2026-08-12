from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .investigation import investigate
from .models import (
    CustomerInvestigationResponse,
    InvestigationRequest,
    InvestigationResponse,
    TraceInvestigationRequest,
)
from .policies import to_customer_response
from .telemetry_investigation import investigate_from_trace

app = FastAPI(
    title="ProdMind",
    version="0.1.0",
    description="Evidence-first AI production support engineer.",
)

# The demo UI runs on a different localhost port. Production deployments should
# replace this with an explicit allow-list for the host application's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8090", "http://127.0.0.1:8090"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
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


# Customer-facing endpoints deliberately return a reduced response model. The
# embedded widget should use only /support endpoints.
@app.post("/api/v1/support", response_model=CustomerInvestigationResponse)
def support_failure(request: InvestigationRequest) -> CustomerInvestigationResponse:
    return to_customer_response(investigate(request))


@app.post("/api/v1/support/trace", response_model=CustomerInvestigationResponse)
async def support_trace(request: TraceInvestigationRequest) -> CustomerInvestigationResponse:
    result = await investigate_from_trace(request)
    return to_customer_response(result)


# Engineer endpoints retain raw evidence. Production deployments must protect
# these endpoints with their normal authentication/authorization layer.
@app.post("/api/v1/investigate", response_model=InvestigationResponse)
def investigate_failure(request: InvestigationRequest) -> InvestigationResponse:
    return investigate(request)


@app.post("/api/v1/investigate/trace", response_model=InvestigationResponse)
async def investigate_trace(request: TraceInvestigationRequest) -> InvestigationResponse:
    return await investigate_from_trace(request)
