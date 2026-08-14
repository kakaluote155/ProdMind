from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .ai_investigator import (
    InvestigatorSessionConflict,
    InvestigatorSessionLimit,
    InvestigatorSessionUnavailable,
    run_investigator_turn,
)
from .changes import configured_change_store
from .config import (
    configured_cors_origins,
    configured_trusted_hosts,
    production_readiness_issues,
)
from .engineer_ui import ENGINEER_UI_HTML
from .evidence_graph import build_evidence_graph
from .investigation import investigate
from .models import (
    ChangeEventCreate,
    ChangeEventResponse,
    AIInvestigatorResponse,
    CustomerInvestigationResponse,
    EvidenceGraph,
    InvestigationRequest,
    InvestigationResponse,
    InvestigatorTraceRequest,
    TraceInvestigationRequest,
)
from .llm import (
    ProviderResponseError,
    ProviderUnavailable,
    configured_investigator_provider,
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
from .version import API_VERSION, RELEASE_VERSION

app = FastAPI(
    title="ProdMind",
    version=RELEASE_VERSION,
    description="Evidence-first AI production support engineer.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "X-ProdMind-Project",
        "X-ProdMind-Engineer-Key",
    ],
)

_trusted_hosts = configured_trusted_hosts()
if _trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_trusted_hosts)


ProjectHeader = Annotated[str | None, Header(alias="X-ProdMind-Project")]
_engineer_key_scheme = APIKeyHeader(name="X-ProdMind-Engineer-Key", auto_error=False)
EngineerHeader = Annotated[str | None, Security(_engineer_key_scheme)]


@app.middleware("http")
async def add_api_version_header(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    if request.url.path.startswith(f"/api/{API_VERSION}/"):
        response.headers["X-ProdMind-API-Version"] = API_VERSION
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path == "/engineer":
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers["X-Frame-Options"] = "DENY"
    return response


def require_project(project_header: ProjectHeader = None) -> str:
    try:
        return validate_project_id(project_header)
    except InvalidProjectId as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid X-ProdMind-Project header is required.",
        ) from exc


def require_engineer(
    project_id: Annotated[str, Depends(require_project)],
    engineer_header: EngineerHeader = None,
) -> None:
    try:
        verify_engineer_key(engineer_header, project_id=project_id)
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
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Trace is not available for this project.",
    )


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "ProdMind",
        "tagline": "Software that knows why it broke — or why it got slow.",
        "version": RELEASE_VERSION,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(response: Response) -> dict[str, str | list[str]]:
    issues = production_readiness_issues()
    if issues:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "issues": issues}
    return {"status": "ready"}


@app.get("/engineer", response_class=HTMLResponse)
def engineer_evidence_graph_viewer() -> HTMLResponse:
    return HTMLResponse(ENGINEER_UI_HTML)


@app.post("/api/v1/support", response_model=CustomerInvestigationResponse)
def support_failure(
    request: InvestigationRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> CustomerInvestigationResponse:
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
    "/api/v1/changes",
    response_model=ChangeEventResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_engineer)],
)
def record_change(
    event: ChangeEventCreate,
    project_id: Annotated[str, Depends(require_project)],
) -> ChangeEventResponse:
    """Record compact deployment/config metadata from trusted delivery tooling."""

    return configured_change_store().record(project_id=project_id, event=event)


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
    try:
        result = await investigate_from_trace(request, project_id=project_id)
    except TraceAccessError as exc:
        raise trace_not_available() from exc
    return build_evidence_graph(result)


@app.post(
    "/api/v1/investigator/trace",
    response_model=AIInvestigatorResponse,
    dependencies=[Depends(require_engineer)],
)
async def investigate_trace_with_ai(
    request: InvestigatorTraceRequest,
    project_id: Annotated[str, Depends(require_project)],
) -> AIInvestigatorResponse:
    """Explain a current trace investigation without allowing AI to replace RCA."""

    trace_request = TraceInvestigationRequest(
        trace_id=request.trace_id,
        question=request.question,
        action=request.action,
        page=request.page,
    )
    try:
        provider = configured_investigator_provider()
        investigation = await investigate_from_trace(trace_request, project_id=project_id)
        return await run_investigator_turn(
            request,
            project_id=project_id,
            investigation=investigation,
            provider=provider,
        )
    except TraceAccessError as exc:
        raise trace_not_available() from exc
    except InvestigatorSessionUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investigator session is not available for this project.",
        ) from exc
    except (InvestigatorSessionLimit, InvestigatorSessionConflict) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Investigator session cannot accept this turn.",
        ) from exc
    except ProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI Investigator provider is not configured or available.",
        ) from exc
    except ProviderResponseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI Investigator returned an unusable response.",
        ) from exc
