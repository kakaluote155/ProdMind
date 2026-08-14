export type FetchLike = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export type ProdMindConfig = {
  apiUrl: string;
  projectId: string;
  transport?: FetchLike;
  pageProvider?: () => string | undefined;
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

export type ProdMindTraceContext = {
  traceId: string;
  traceparent: string;
};

export class ProdMindRequestError extends Error {
  readonly status: number;

  constructor(status: number) {
    super(`ProdMind request failed: ${status}`);
    this.name = "ProdMindRequestError";
    this.status = status;
  }
}

export class ProdMindClient {
  readonly apiUrl: string;
  readonly projectId: string;

  private readonly transport: FetchLike;
  private readonly pageProvider: () => string | undefined;
  private latestAction: UserActionContext | null = null;

  constructor(nextConfig: ProdMindConfig) {
    const normalized = normalizeConfig(nextConfig);
    this.apiUrl = normalized.apiUrl;
    this.projectId = normalized.projectId;
    this.transport = normalized.transport;
    this.pageProvider = normalized.pageProvider;
  }

  trackAction(action: UserActionContext): void {
    this.latestAction = normalizeAction(action);
  }

  getLatestAction(): UserActionContext | null {
    return this.latestAction ? { ...this.latestAction } : null;
  }

  clearLatestAction(): void {
    this.latestAction = null;
  }

  /**
   * Fetch wrapper that creates or preserves valid W3C trace context before the
   * host request leaves the browser. Request bodies and arbitrary headers are
   * never copied into ProdMind action context.
   */
  async fetch(
    action: string,
    input: RequestInfo | URL,
    init: RequestInit = {},
  ): Promise<Response> {
    return executeTrackedFetch({
      action,
      input,
      init,
      transport: this.transport,
      page: this.pageProvider(),
      track: (context) => this.trackAction(context),
    });
  }

  /** Ask the customer-safe ProdMind endpoint about the latest action. */
  async ask(question: string): Promise<CustomerInvestigation> {
    const normalizedQuestion = requireText(question, "question", 2000);
    const action = this.latestAction;
    if (!action) {
      throw new Error("ProdMind has no user action to investigate yet.");
    }

    const hasTrace = action.traceId !== undefined;
    const endpoint = hasTrace
      ? `${this.apiUrl}/api/v1/support/trace`
      : `${this.apiUrl}/api/v1/support`;
    const body = hasTrace
      ? {
          question: normalizedQuestion,
          action: action.action,
          page: action.page,
          trace_id: action.traceId,
        }
      : {
          question: normalizedQuestion,
          action: action.action,
          page: action.page,
          request_id: action.requestId,
          http_status: action.httpStatus,
        };

    const response = await this.transport(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-ProdMind-Project": this.projectId,
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new ProdMindRequestError(response.status);
    }
    return response.json() as Promise<CustomerInvestigation>;
  }
}

let defaultClient: ProdMindClient | null = null;
let pendingAction: UserActionContext | null = null;

/** Create an isolated client for one ProdMind project. */
export function createProdMindClient(config: ProdMindConfig): ProdMindClient {
  return new ProdMindClient(config);
}

/** Initialize the backwards-compatible default client. */
export function initProdMind(nextConfig: ProdMindConfig): ProdMindClient {
  const previousAction = defaultClient?.getLatestAction() ?? pendingAction;
  defaultClient = createProdMindClient(nextConfig);
  if (previousAction) defaultClient.trackAction(previousAction);
  pendingAction = null;
  return defaultClient;
}

export function trackAction(action: UserActionContext): void {
  if (defaultClient) {
    defaultClient.trackAction(action);
    return;
  }
  pendingAction = normalizeAction(action);
}

export function getLatestAction(): UserActionContext | null {
  const action = defaultClient?.getLatestAction() ?? pendingAction;
  return action ? { ...action } : null;
}

export function clearLatestAction(): void {
  defaultClient?.clearLatestAction();
  pendingAction = null;
}

/** Backwards-compatible tracked fetch using the default client when available. */
export async function prodMindFetch(
  action: string,
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  if (defaultClient) return defaultClient.fetch(action, input, init);
  return executeTrackedFetch({
    action,
    input,
    init,
    transport: requireGlobalFetch(),
    page: defaultPage(),
    track: trackAction,
  });
}

export async function askProdMind(question: string): Promise<CustomerInvestigation> {
  if (!defaultClient) {
    throw new Error("ProdMind is not initialized. Call initProdMind() first.");
  }
  return defaultClient.ask(question);
}

export function createTraceparent(): ProdMindTraceContext {
  const traceId = randomHex(16);
  const spanId = randomHex(8);
  return {
    traceId,
    traceparent: `00-${traceId}-${spanId}-01`,
  };
}

type TrackedFetchInput = {
  action: string;
  input: RequestInfo | URL;
  init: RequestInit;
  transport: FetchLike;
  page: string | undefined;
  track: (context: UserActionContext) => void;
};

async function executeTrackedFetch(options: TrackedFetchInput): Promise<Response> {
  const action = requireText(options.action, "action", 300);
  const headers = new Headers(options.init.headers);
  let traceId = parseTraceId(headers.get("traceparent"));
  if (!traceId) {
    const context = createTraceparent();
    traceId = context.traceId;
    headers.set("traceparent", context.traceparent);
  }

  let requestId = headers.get("X-Request-Id")?.trim();
  if (!requestId) {
    requestId = createRequestId();
    headers.set("X-Request-Id", requestId);
  }

  const baseContext = {
    action,
    page: options.page,
    requestId,
    traceId,
  };
  try {
    const response = await options.transport(options.input, {
      ...options.init,
      headers,
    });
    options.track({ ...baseContext, httpStatus: response.status });
    return response;
  } catch (error) {
    options.track(baseContext);
    throw error;
  }
}

function normalizeConfig(config: ProdMindConfig): {
  apiUrl: string;
  projectId: string;
  transport: FetchLike;
  pageProvider: () => string | undefined;
} {
  const apiUrl = requireText(config.apiUrl, "apiUrl", 2000).replace(/\/+$/, "");
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(config.projectId)) {
    throw new Error("ProdMind projectId is invalid.");
  }
  return {
    apiUrl,
    projectId: config.projectId,
    transport: config.transport ?? requireGlobalFetch(),
    pageProvider: config.pageProvider ?? defaultPage,
  };
}

function normalizeAction(action: UserActionContext): UserActionContext {
  const normalized: UserActionContext = {
    action: requireText(action.action, "action", 300),
    occurredAt: action.occurredAt ?? new Date().toISOString(),
  };
  if (action.page !== undefined) normalized.page = optionalText(action.page, "page", 500);
  if (action.requestId !== undefined) {
    normalized.requestId = optionalText(action.requestId, "requestId", 500);
  }
  if (action.traceId !== undefined) {
    const traceId = action.traceId.toLowerCase();
    if (!/^[0-9a-f]{32}$/.test(traceId) || /^0{32}$/.test(traceId)) {
      throw new Error("ProdMind traceId must be a non-zero 32-character hex value.");
    }
    normalized.traceId = traceId;
  }
  if (action.httpStatus !== undefined) {
    if (!Number.isInteger(action.httpStatus) || action.httpStatus < 100 || action.httpStatus > 599) {
      throw new Error("ProdMind httpStatus must be an integer from 100 to 599.");
    }
    normalized.httpStatus = action.httpStatus;
  }
  return normalized;
}

function parseTraceId(traceparent: string | null): string | undefined {
  if (!traceparent) return undefined;
  const match = /^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$/i.exec(
    traceparent.trim(),
  );
  if (!match || /^0{32}$/.test(match[1]) || /^0{16}$/.test(match[2])) return undefined;
  return match[1].toLowerCase();
}

function requireText(value: string, name: string, maxLength: number): string {
  const normalized = value.trim();
  if (!normalized || normalized.length > maxLength) {
    throw new Error(`ProdMind ${name} must contain 1-${maxLength} characters.`);
  }
  return normalized;
}

function optionalText(value: string, name: string, maxLength: number): string {
  if (value.length > maxLength) {
    throw new Error(`ProdMind ${name} must not exceed ${maxLength} characters.`);
  }
  return value;
}

function createRequestId(): string {
  const cryptoApi = requireCrypto();
  return typeof cryptoApi.randomUUID === "function"
    ? cryptoApi.randomUUID()
    : randomHex(16);
}

function randomHex(byteLength: number): string {
  const bytes = new Uint8Array(byteLength);
  requireCrypto().getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function requireCrypto(): Crypto {
  if (!globalThis.crypto?.getRandomValues) {
    throw new Error("ProdMind requires the Web Crypto API.");
  }
  return globalThis.crypto;
}

function requireGlobalFetch(): FetchLike {
  if (typeof globalThis.fetch !== "function") {
    throw new Error("ProdMind requires fetch or a configured transport.");
  }
  return globalThis.fetch.bind(globalThis);
}

function defaultPage(): string | undefined {
  return typeof window !== "undefined" ? window.location.pathname : undefined;
}
