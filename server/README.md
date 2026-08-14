# ProdMind Server

FastAPI service responsible for investigation orchestration, normalized evidence and response generation.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install "fastapi>=0.116,<1.0" "uvicorn[standard]>=0.35,<1.0" "pydantic>=2.11,<3.0"
uvicorn app.main:app --reload --port 8088
```

API documentation:

```text
http://localhost:8088/docs
```

## Current API

- `GET /health`
- `POST /api/v1/support/trace`
- `POST /api/v1/investigate/trace`
- `POST /api/v1/investigate/trace/graph`
- `POST /api/v1/investigator/trace`

Deterministic RCA remains authoritative. The optional AI Investigator is disabled
by default and only explains an existing trace investigation.

```text
PRODMIND_LLM_PROVIDER=openai
PRODMIND_LLM_MODEL=<structured-output-capable-model>
PRODMIND_LLM_API_KEY=<secret>
```

The provider must return schema-constrained, Evidence-ID-cited engineer claims
and fixed-enum read-only next steps.

All `/api/v1/*` responses include `X-ProdMind-API-Version: v1`. The public
OpenAPI contract is reviewed in `docs/openapi-v1.json` and protected by a schema
snapshot test; see `docs/api-compatibility.md` for the compatibility policy.

## Verification

```bash
pytest -q
python -m app.ai_eval
```

The second command runs the provider-independent AI authority, grounding,
read-only and context-minimization quality gates used by CI.

Tempo project isolation prefers `prodmind.project.id` as a resource attribute.
The supported packages under `integrations/` can attach the same value from
server configuration to the current HTTP server span when framework-owned
instrumentation controls the resource. Missing and conflicting scopes fail closed.
