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
- `POST /api/v1/investigate`

The current investigator is intentionally deterministic. Real telemetry collection will be added behind connector interfaces before model-assisted reasoning is introduced.
