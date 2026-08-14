# AI Investigator

ProdMind's optional AI Investigator explains an investigation that has already
been performed by the evidence and RCA pipeline. It is not a second root-cause
engine.

## Authority boundary

```text
Project-authorized telemetry
        ↓
Deterministic RCA
        ↓
Minimized normalized evidence packet
        ↓
Optional AI explanation
```

The current `InvestigationResponse.status` and `root_cause` are authoritative.
The provider cannot return a replacement root-cause field. If deterministic RCA
returns `insufficient_evidence`, the AI must preserve that conclusion and may
only describe the evidence gap.

The API is engineer-only:

```http
POST /api/v1/investigator/trace
X-ProdMind-Project: <project-id>
X-ProdMind-Engineer-Key: <engineer-key>
```

Request:

```json
{
  "trace_id": "<authorized-trace-id>",
  "question": "Explain the verified cause and what to inspect next.",
  "action": "create-user",
  "session_id": null
}
```

Use the returned `session_id` for a follow-up question about the same project and
trace. A session ID cannot be reused across another project or trace.

## Grounding contract

The provider receives numbered evidence references such as `E1`, `E2` and must
return strict structured output:

```text
answer
claims[]
  summary
  evidence_ids[]
missing_evidence[]
next_steps[]
```

ProdMind rejects a provider response when a claim cites an Evidence ID that was
not supplied. A diagnosed investigation must contain at least one cited claim,
and the cited set must include evidence emitted by the authoritative RCA rule.
User action or HTTP status evidence alone cannot stand in for root-cause evidence.

When deterministic RCA returns `insufficient_evidence`, provider claims are
rejected. ProdMind returns its deterministic engineer explanation while retaining
only the provider's bounded evidence gaps and read-only next-step enum values.

Citation validation proves that a claim points to available evidence; it does
not prove semantic entailment by itself. Provider/model-specific semantic
evaluations are required by the v1.0 CI and release build.

## Evaluations and quality gates

The deterministic evaluation set is stored in `server/app/ai_eval_cases.json`. It
covers authoritative RCA citation, fabricated citations, weak symptom-only
citations, insufficient-evidence authority, forbidden remediation steps,
root-cause replacement attempts and default context minimization.

Run it from `server/`:

```bash
python -m app.ai_eval
```

The command exits non-zero when a safety case fails and runs as a separate CI
quality gate in addition to the normal Python test suite. These deterministic
fixtures do not replace future provider/model-specific semantic evaluations;
they enforce the provider-independent safety contract.

## Read-only planning

The model receives no executable tools. `next_steps` is restricted to:

```text
inspect_trace
inspect_logs
inspect_metrics
inspect_changes
inspect_history
ask_for_context
```

The AI Investigator cannot restart services, run shell commands, modify a
database, change configuration, deploy, or invoke remediation.

## Context minimization

The default provider packet excludes:

- Trace IDs;
- raw Loki log lines and stack traces;
- Change Event details;
- Incident Memory details;
- request bodies, form values and credentials.

A compact count of correlated logs may be included. Operators can explicitly opt
in to compact Change or Incident Memory context with:

```text
PRODMIND_LLM_INCLUDE_CHANGE_CONTEXT=true
PRODMIND_LLM_INCLUDE_INCIDENT_MEMORY=true
```

These settings do not change causality: Change remains temporal context and
history remains supporting context.

## Providers

Default:

```text
PRODMIND_LLM_PROVIDER=disabled
```

OpenAI Responses provider:

```text
PRODMIND_LLM_PROVIDER=openai
PRODMIND_LLM_MODEL=<structured-output-capable-model>
PRODMIND_LLM_API_KEY=<secret>
PRODMIND_LLM_BASE_URL=https://api.openai.com/v1
```

The adapter uses strict JSON Schema structured output and sends `store: false`.
ProdMind resends only its own compact conversation history instead of retaining a
provider response chain. See the official OpenAI documentation for
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
and [conversation state/data retention](https://developers.openai.com/api/docs/guides/conversation-state).

Provider configuration fails closed. Missing credentials/model configuration
return `503`; unusable provider output returns `502`.

## Session state

Sessions are kept in process memory and are:

- bound to one project and trace;
- limited to eight turns by default;
- expired after 30 minutes by default;
- globally bounded in count;
- updated only after a valid grounded provider response.

Configure limits with:

```text
PRODMIND_AI_SESSION_TTL_SECONDS=1800
PRODMIND_AI_SESSION_MAX_TURNS=8
PRODMIND_AI_SESSION_MAX_COUNT=1024
```

This first store is suitable for a single-process prototype. A production
multi-replica deployment will require an encrypted/shared state backend or a
stateless signed-history design.
