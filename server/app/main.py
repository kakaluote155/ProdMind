from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .engineer_ui import ENGINEER_UI_HTML
from .evidence_graph import build_evidence_graph
from .investigation import investigate
from .models import (
    CustomerInvestigationResponse,
    EvidenceGraph,
    InvestigationRequest,
    InvestigationResponse,
    TraceInvestigationRequest,
)
from .policies import to_customer_response
from .security import (
    EngineerAuthUnavailable,
    InvalidEngineerKey,
    InvalidProjectId,
    validate_project_id,
    verify_engineer_key,
)
from .telemetry_investigation import TraceAccessError, investigate_from_trace

app = FastAPI(
    title="ProdMind",
    version="0.2.0",
    description="Evidence-first AI production support engineer.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8090", "http://127.0.0.1:8090"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


ProjectHeader = Annotated[str | None, Header(alias="X-ProdMind-Project")]
EngineerHeader = Annotated[str | None, Header(alias="X-ProdMind-Engineer-Key")]


def require_project(project_header: ProjectHeader = None) -> str:
    try:
        return validate_project_id(project_header)
    except InvalidProjectId as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid X-ProdMind-Project header is required.",
        ) from exc


def require_engineer(engineer_header: EngineerHeader = None) -> None:
    try:
        verify_engineer_key(engineer_header)
    except EngineerAuthUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Engineer API authentication is not configured.",
        ) from exc
    except InvalidEngineerKey as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Engineer authentication failed.",
        ) from exc


def trace_not_available() -> HTTPException:
    # Use one generic response for missing, unscoped and cross-project traces so
    # callers cannot use ProdMind as a trace-enumeration oracle.
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Trace is not available for this project.",
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "ProdMind",
        "tagline": "Software that knows why it broke.",
        "version": "0.2.0",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/engineer", response_class=HTMLResponse)
def engineer_evidence_graph_viewer() -> HTMLResponse:
    """Serve the empty engineer graph shell.

    The page itself contains no evidence. Loading graph data still requires both
    X-ProdMind-Project and X-ProdMind-Engineer-Key on the API request.
    """

    return HTMLResponse(ENGINEER_UI_HTML)


@app.post("/api/v1/support", response_model=CustomerInvestigationResponse)
def support_failure(
    request: InvestigationRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> CustomerInvestigationResponse:
    # project_id is validated even when this deterministic endpoint does not yet
    # access project-scoped telemetry.
    _ = project_id
    return to_customer_response(investigate(request))


@app.post("/api/v1/support/trace", response_model=CustomerInvestigationResponse)
async def support_trace(
    request: TraceInvestigationRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> CustomerInvestigationResponse:
    try:
        result = await investigate_from_trace(request, project_id=project_id)
    except TraceAccessError as exc:
        raise trace_not_available() from exc
    return to_customer_response(result)


@app.post(
    "/api/v1/investigate",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_engineer)],
)
def investigate_failure(
    request: InvestigationRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> InvestigationResponse:
    _ = project_id
    return investigate(request)


@app.post(
    "/api/v1/investigate/trace",
    response_model=InvestigationResponse,
    dependencies=[Depends(require_engineer)],
)
async def investigate_trace(
    request: TraceInvestigationRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> InvestigationResponse:
    try:
        return await investigate_from_trace(request, project_id=project_id)
    except TraceAccessError as exc:
        raise trace_not_available() from exc


@app.post(
    "/api/v1/investigate/trace/graph",
    response_model=EvidenceGraph,
    dependencies=[Depends(require_engineer)],
)
async def investigate_trace_graph(
    request: TraceInvestigationRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> EvidenceGraph:
    """Build an engineer-only explanation graph for an authorized trace."""

    try:
        result = await investigate_from_trace(request, project_id=project_id)
    except TraceAccessError as exc:
        raise trace_not_available() from exc
    return build_evidence_graph(result)
