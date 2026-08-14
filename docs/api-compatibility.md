# API compatibility

ProdMind's public HTTP surface is versioned in the path. The current contract is
`/api/v1/*`; successful and error responses on that surface include:

```text
X-ProdMind-API-Version: v1
```

## v1 compatibility policy

Within v1, maintainers may add optional request fields, new endpoints, new
optional response fields and new enum values only after evaluating strict-client
impact. The following require a new API version or an explicitly documented
migration window:

- removing or renaming an endpoint, field or required header;
- changing a field's type or meaning;
- making an optional request field required;
- weakening customer/engineer response separation;
- changing project-isolation or authentication semantics;
- reusing an RCA category for a different diagnosis.

Security fixes may intentionally tighten validation or authorization without a
new path version. Such changes must be called out in release notes.

## Contract snapshot

The reviewed OpenAPI contract is stored at `docs/openapi-v1.json`. CI compares
the running FastAPI schema with this snapshot so incidental model or route drift
fails tests.

For an intentional compatible change:

1. update implementation and positive/negative security tests;
2. review the generated schema and this compatibility policy;
3. run `python scripts/update-openapi-contract.py`;
4. include the schema diff in review and update release notes.

The snapshot freezes the machine-readable shape; it does not replace behavioral,
authorization, project-isolation or customer-redaction tests.
