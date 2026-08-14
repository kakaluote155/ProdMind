# @prodmind/widget

Minimal browser SDK for connecting a user's action and W3C trace context to
ProdMind's customer-safe investigation API.

## Instance API

Use one client per project/runtime boundary:

```ts
import { createProdMindClient } from "@prodmind/widget";

const prodmind = createProdMindClient({
  apiUrl: "https://support.example.com",
  projectId: "customer-portal",
});

const response = await prodmind.fetch(
  "create-user",
  "/api/users",
  {
    method: "POST",
    body: JSON.stringify(formData),
    headers: { "Content-Type": "application/json" },
  },
);

if (!response.ok) {
  const explanation = await prodmind.ask("Why did my last operation fail?");
  showCustomerSafeMessage(explanation.answer);
}
```

`prodmind.fetch()` creates a valid W3C `traceparent` unless the host already
provided one, adds an `X-Request-Id`, and remembers only:

- action name;
- page path;
- request ID;
- trace ID;
- HTTP status;
- occurrence time.

It never copies request bodies, form fields, cookies, authorization headers or
arbitrary headers into action context. Network failures still retain the trace
and request correlation context before the original error is rethrown.

`createProdMindClient()` instances keep project and latest-action state isolated.
The earlier `initProdMind`, `prodMindFetch`, `trackAction` and `askProdMind`
functions remain available as a backwards-compatible default-client API.

## Manual correlation

For applications that use their own HTTP wrapper:

```ts
const { traceId, traceparent } = createTraceparent();

await hostRequest({ headers: { traceparent } });

prodmind.trackAction({
  action: "submit-order",
  traceId,
  httpStatus: 500,
});
```

Trace IDs must be non-zero 32-character hexadecimal W3C identifiers. Project
IDs are validated using the same public format as the ProdMind server.

## Verification

```bash
npm install
npm run typecheck
npm test
npm run build
```
