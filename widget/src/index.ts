export type ProdMindConfig = {
  apiUrl: string;
  projectId: string;
};

export type UserActionContext = {
  action: string;
  page?: string;
  requestId?: string;
  traceId?: string;
  httpStatus?: number;
  occurredAt?: string;
};

export type CustomerInvestigation = {
  incident_id: string;
  status: "diagnosed" | "insufficient_evidence";
  category?: string | null;
  confidence?: number | null;
  answer: string;
};

let config: ProdMindConfig | null = null;
let latestAction: UserActionContext | null = null;

export function initProdMind(nextConfig: ProdMindConfig): void {
  config = {
    ...nextConfig,
    apiUrl: nextConfig.apiUrl.replace(/\/$/, ""),
  };
}

export function trackAction(action: UserActionContext): void {
  latestAction = {
    ...action,
    occurredAt: action.occurredAt ?? new Date().toISOString(),
  };
}

export function getLatestAction(): UserActionContext | null {
  return latestAction ? { ...latestAction } : null;
}

/**
 * Fetch wrapper for host applications.
 *
 * ProdMind creates a W3C trace context before the request leaves the browser.
 * OpenTelemetry-instrumented backends continue that trace, so ProdMind already
 * knows which trace belongs to the user's action even if the API returns only a
 * generic error. Request bodies are never copied into ProdMind action context.
 */
export async function prodMindFetch(
  action: string,
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const traceId = randomHex(16);
  const parentSpanId = randomHex(8);
  const headers = new Headers(init.headers);

  if (!headers.has("traceparent")) {
    headers.set("traceparent", `00-${traceId}-${parentSpanId}-01`);
  }

  const requestId = headers.get("X-Request-Id") ?? crypto.randomUUID();
  if (!headers.has("X-Request-Id")) {
    headers.set("X-Request-Id", requestId);
  }

  const response = await fetch(input, { ...init, headers });
  const propagatedTraceId = parseTraceId(headers.get("traceparent")) ?? traceId;

  trackAction({
    action,
    page: typeof window !== "undefined" ? window.location.pathname : undefined,
    requestId,
    traceId: propagatedTraceId,
    httpStatus: response.status,
  });

  return response;
}

/** Ask the customer-safe ProdMind endpoint about the latest tracked action. */
export async function askProdMind(question: string): Promise<CustomerInvestigation> {
  if (!config) {
    throw new Error("ProdMind is not initialized. Call initProdMind() first.");
  }
  if (!latestAction) {
    throw new Error("ProdMind has no user action to investigate yet.");
  }

  const endpoint = latestAction.traceId
    ? `${config.apiUrl}/api/v1/support/trace`
    : `${config.apiUrl}/api/v1/support`;

  const body = latestAction.traceId
    ? {
        question,
        action: latestAction.action,
        page: latestAction.page,
        trace_id: latestAction.traceId,
      }
    : {
        question,
        action: latestAction.action,
        page: latestAction.page,
        request_id: latestAction.requestId,
        http_status: latestAction.httpStatus,
      };

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-ProdMind-Project": config.projectId,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`ProdMind request failed: ${response.status}`);
  }

  return response.json() as Promise<CustomerInvestigation>;
}

export function createTraceparent(): { traceId: string; traceparent: string } {
  const traceId = randomHex(16);
  const spanId = randomHex(8);
  return {
    traceId,
    traceparent: `00-${traceId}-${spanId}-01`,
  };
}

function parseTraceId(traceparent: string | null): string | undefined {
  if (!traceparent) return undefined;
  const parts = traceparent.trim().split("-");
  if (parts.length !== 4 || parts[1].length !== 32) return undefined;
  return parts[1].toLowerCase();
}

function randomHex(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}
