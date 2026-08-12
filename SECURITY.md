# Security

ProdMind is designed to inspect production evidence, so security boundaries are part of the product rather than an optional add-on.

## Current security model

ProdMind v0.1 is **read-only by design**.

The project must not automatically execute remediation commands or modify production resources.

## Sensitive data

Connectors and client SDKs should minimize collection and redact sensitive values before persistence or model access.

Examples include:

- passwords
- access tokens
- API keys
- cookies and authorization headers
- database credentials
- private keys
- personal data not required for diagnosis

## Response separation

Customer-facing responses must not expose internal hostnames, IP addresses, SQL statements, stack traces, secrets, source paths or infrastructure topology.

Engineer-level information should only be available to authorized users.

## Reporting vulnerabilities

Please do not publish exploitable security issues in a public GitHub issue.

Until a dedicated security contact is configured, open a minimal issue asking for a private security contact without including exploit details.
