import type { AuthSession, BacktestTask, PaperOrder, ParseResult, StrategySpec, Template, VersionItem } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
const TOKEN_KEY = "quantpartner:auth-token:v1";

export function getAccessToken(): string | null {
  return typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAccessToken();
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `请求失败 (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export async function registerAccount(payload: { email: string; password: string; display_name: string; workspace_name: string }): Promise<AuthSession> {
  const session = await request<AuthSession>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(payload) });
  if (session.access_token) setAccessToken(session.access_token);
  return session;
}

export async function loginAccount(email: string, password: string): Promise<AuthSession> {
  const session = await request<AuthSession>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
  if (session.access_token) setAccessToken(session.access_token);
  return session;
}

export function getMe(): Promise<AuthSession> {
  return request("/api/v1/auth/me");
}

export async function logoutAccount(): Promise<void> {
  try {
    await request("/api/v1/auth/logout", { method: "POST" });
  } finally {
    setAccessToken(null);
  }
}

export function getTemplates(): Promise<Template[]> {
  return request("/api/v1/templates");
}

export function parseStrategy(text: string): Promise<ParseResult> {
  return request("/api/v1/strategy/parse", { method: "POST", body: JSON.stringify({ text }) });
}

export function createStrategy(spec: StrategySpec): Promise<{ id: string; latest_version_id: string }> {
  return request("/api/v1/strategies", {
    method: "POST",
    body: JSON.stringify({ name: spec.name, spec }),
  });
}

export function saveVersion(strategyId: string, spec: StrategySpec): Promise<VersionItem> {
  return request(`/api/v1/strategies/${strategyId}/versions`, {
    method: "POST",
    body: JSON.stringify({ spec, note: "参数调整" }),
  });
}

export function listVersions(strategyId: string): Promise<VersionItem[]> {
  return request(`/api/v1/strategies/${strategyId}/versions`);
}

export function submitBacktest(spec: StrategySpec, strategyId?: string): Promise<BacktestTask> {
  return request("/api/v1/backtests", {
    method: "POST",
    body: JSON.stringify({ spec, strategy_id: strategyId, idempotency_key: crypto.randomUUID() }),
  });
}

export function getBacktest(id: string): Promise<BacktestTask> {
  return request(`/api/v1/backtests/${id}`);
}

export async function cancelBacktest(id: string): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`${API_URL}/api/v1/backtests/${id}`, { method: "DELETE", headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!response.ok) throw new Error("终止回测失败");
}

export function listPaperOrders(): Promise<PaperOrder[]> {
  return request("/api/v1/paper/orders");
}

export function createPaperOrder(payload: { market: "CN_A" | "HK" | "US"; symbol: string; side: "buy" | "sell"; order_type: "market" | "limit"; quantity: number; limit_price?: number }): Promise<PaperOrder> {
  return request("/api/v1/paper/orders", { method: "POST", body: JSON.stringify({ ...payload, client_order_id: crypto.randomUUID() }) });
}

export function cancelPaperOrder(id: string): Promise<PaperOrder> {
  return request(`/api/v1/paper/orders/${id}`, { method: "DELETE" });
}
