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

let config: ProdMindConfig | null = null;
let latestAction: UserActionContext | null = null;

export function initProdMind(nextConfig: ProdMindConfig): void {
  config = nextConfig;
}

export function trackAction(action: UserActionContext): void {
  latestAction = {
    ...action,
    occurredAt: action.occurredAt ?? new Date().toISOString(),
  };
}

export function getLatestAction(): UserActionContext | null {
  return latestAction;
}

export async function askProdMind(question: string): Promise<unknown> {
  if (!config) {
    throw new Error("ProdMind is not initialized. Call initProdMind() first.");
  }

  const response = await fetch(`${config.apiUrl}/api/v1/investigate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-ProdMind-Project": config.projectId,
    },
    body: JSON.stringify({
      question,
      action: latestAction?.action,
      page: latestAction?.page,
      request_id: latestAction?.requestId,
      trace_id: latestAction?.traceId,
      http_status: latestAction?.httpStatus,
    }),
  });

  if (!response.ok) {
    throw new Error(`ProdMind request failed: ${response.status}`);
  }

  return response.json();
}
