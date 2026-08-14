# ProdMind Python integration

This package tags the current OpenTelemetry HTTP server span with a
server-configured ProdMind project ID. It does not read the project from a
request header and does not inspect bodies, form values, cookies or headers.

```bash
pip install prodmind-integration
```

ASGI/FastAPI example:

```python
from fastapi import FastAPI
from prodmind_integration import ProdMindASGIMiddleware

app = FastAPI()
app.add_middleware(ProdMindASGIMiddleware, project_id="customer-portal")
```

Install this middleware inside your OpenTelemetry ASGI/FastAPI instrumentation
so a current server span exists. Resource configuration is preferred when you
control it:

```text
OTEL_RESOURCE_ATTRIBUTES=prodmind.project.id=customer-portal
```

Manual instrumentation can call `mark_current_span("customer-portal")` after
starting a server span.
