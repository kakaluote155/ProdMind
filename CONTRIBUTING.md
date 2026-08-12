# Contributing to ProdMind

ProdMind is in early development. Small, testable contributions are preferred over large framework rewrites.

## Development principles

1. **Evidence before explanation.** Do not claim a root cause without supporting evidence.
2. **Read-only by default.** New integrations must not mutate production systems unless a future remediation design explicitly permits it.
3. **Fail safely.** `insufficient_evidence` is better than a confident hallucination.
4. **Protect customer data.** Avoid collecting or exposing secrets and unnecessary personal data.
5. **Keep connectors normalized.** Provider-specific payloads should be converted into ProdMind evidence models.

## Local server

```bash
cd server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install "fastapi>=0.116,<1.0" "uvicorn[standard]>=0.35,<1.0" "pydantic>=2.11,<3.0" "pytest>=8.4,<9.0" "httpx>=0.28,<1.0"
uvicorn app.main:app --reload --port 8088
```

## Tests

```bash
cd server
pytest -q
```

## Pull requests

Please include:

- what production problem the change solves;
- what evidence is used;
- how failure/insufficient evidence is handled;
- tests for new diagnosis logic;
- any security or privacy implications.
