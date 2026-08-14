import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ProdMindRequestError,
  clearLatestAction,
  createProdMindClient,
  createTraceparent,
  getLatestAction,
  initProdMind,
  trackAction,
} from "./index";

const customerResponse = {
  incident_id: "PM-TEST",
  status: "diagnosed" as const,
  category: "database_unique_violation",
  confidence: 0.98,
  answer: "The submitted information already exists.",
};

afterEach(() => {
  clearLatestAction();
  vi.restoreAllMocks();
});

describe("trace context", () => {
  it("creates valid non-zero W3C trace context", () => {
    const context = createTraceparent();
    expect(context.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(context.traceId).not.toBe("0".repeat(32));
    expect(context.traceparent).toMatch(/^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
  });

  it("preserves a valid host traceparent and records response status", async () => {
    const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
    const transport = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init });
      return new Response("busy", { status: 503 });
    });
    const client = createProdMindClient({
      apiUrl: "https://prodmind.test/",
      projectId: "project-a",
      transport,
      pageProvider: () => "/checkout",
    });
    const traceparent = "00-11111111111111111111111111111111-2222222222222222-01";

    const response = await client.fetch("submit-order", "https://api.test/orders", {
      headers: { traceparent, "X-Request-Id": "request-1" },
    });

    expect(response.status).toBe(503);
    expect(new Headers(calls[0].init?.headers).get("traceparent")).toBe(traceparent);
    expect(client.getLatestAction()).toMatchObject({
      action: "submit-order",
      page: "/checkout",
      requestId: "request-1",
      traceId: "11111111111111111111111111111111",
      httpStatus: 503,
    });
  });

  it("replaces invalid trace context before sending", async () => {
    let sentHeaders = new Headers();
    const client = createProdMindClient({
      apiUrl: "/prodmind",
      projectId: "project-a",
      transport: vi.fn(async (_input, init) => {
        sentHeaders = new Headers(init?.headers);
        return new Response(null, { status: 204 });
      }),
    });

    await client.fetch("refresh", "/api/data", {
      headers: { traceparent: "00-not-a-trace-123-01" },
    });

    expect(sentHeaders.get("traceparent")).toMatch(
      /^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/,
    );
    expect(sentHeaders.get("X-Request-Id")).toBeTruthy();
  });

  it("retains correlation context when the host request throws", async () => {
    const client = createProdMindClient({
      apiUrl: "/prodmind",
      projectId: "project-a",
      transport: vi.fn(async () => {
        throw new TypeError("network unavailable");
      }),
    });

    await expect(client.fetch("load-dashboard", "/api/data")).rejects.toThrow(
      "network unavailable",
    );
    expect(client.getLatestAction()).toMatchObject({ action: "load-dashboard" });
    expect(client.getLatestAction()?.traceId).toMatch(/^[0-9a-f]{32}$/);
    expect(client.getLatestAction()?.httpStatus).toBeUndefined();
  });
});

describe("customer-safe client", () => {
  it("keeps clients project-isolated and sends only allowlisted action fields", async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = [];
    const transport = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(input), init });
      return Response.json(customerResponse);
    });
    const first = createProdMindClient({
      apiUrl: "https://prodmind.test/",
      projectId: "project-a",
      transport,
    });
    const second = createProdMindClient({
      apiUrl: "https://prodmind.test",
      projectId: "project-b",
      transport,
    });
    first.trackAction({
      action: "create-user",
      traceId: "1".repeat(32),
      ...( { password: "must-not-be-collected" } as object),
    });

    const result = await first.ask("Why did this fail?");

    expect(result).toEqual(customerResponse);
    expect(second.getLatestAction()).toBeNull();
    expect(requests[0].url).toBe("https://prodmind.test/api/v1/support/trace");
    expect(new Headers(requests[0].init?.headers).get("X-ProdMind-Project")).toBe(
      "project-a",
    );
    expect(requests[0].init?.body).not.toContain("password");
    expect(requests[0].init?.body).not.toContain("must-not-be-collected");
  });

  it("uses a typed error without copying the response body", async () => {
    const client = createProdMindClient({
      apiUrl: "/prodmind",
      projectId: "project-a",
      transport: vi.fn(async () => new Response("internal secret", { status: 502 })),
    });
    client.trackAction({ action: "save", requestId: "request-2", httpStatus: 500 });

    const error = await client.ask("Why?").catch((value: unknown) => value);

    expect(error).toBeInstanceOf(ProdMindRequestError);
    const requestError = error as ProdMindRequestError;
    expect(requestError.status).toBe(502);
    expect(requestError.message).not.toContain("internal secret");
  });

  it("preserves the backwards-compatible default API", () => {
    trackAction({ action: "before-init", requestId: "request-3" });
    const client = initProdMind({
      apiUrl: "/prodmind",
      projectId: "project-a",
      transport: vi.fn(),
    });

    expect(getLatestAction()?.action).toBe("before-init");
    expect(client.getLatestAction()?.requestId).toBe("request-3");
  });
});

describe("validation", () => {
  it("fails early for invalid project and trace identifiers", () => {
    expect(() =>
      createProdMindClient({ apiUrl: "/prodmind", projectId: "bad project" }),
    ).toThrow("projectId is invalid");
    const client = createProdMindClient({ apiUrl: "/prodmind", projectId: "valid" });
    expect(() => client.trackAction({ action: "save", traceId: "trace-abc" })).toThrow(
      "32-character hex",
    );
  });
});
