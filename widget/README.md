# @prodmind/widget

Embeddable browser SDK for connecting user-facing failures to ProdMind investigations.

## Current prototype

```ts
import { initProdMind, trackAction, askProdMind } from "@prodmind/widget";

initProdMind({
  apiUrl: "http://localhost:8088",
  projectId: "demo-app",
});

trackAction({
  action: "create-user",
  page: "/users",
  requestId: "req-123",
  traceId: "trace-abc",
  httpStatus: 500,
});

const result = await askProdMind("Why did my last operation fail?");
```

The SDK must remain conservative about data collection. It should capture identifiers and execution context, not arbitrary form values.
