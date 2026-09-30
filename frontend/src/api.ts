import type { Filters } from "./types";

const base = import.meta.env.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getToken(): string | null {
  return localStorage.getItem("cs2_token");
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem("cs2_token", token);
  else localStorage.removeItem("cs2_token");
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${base}${path}`, { ...options, headers });
  if (response.status === 204) return undefined as T;
  const data: { detail?: string } = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Request failed";
    throw new ApiError(response.status, detail);
  }
  return data as T;
}

export function filterQuery(filters: Filters, page: number, sort: string): string {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.weapon) params.set("weapon", filters.weapon);
  if (filters.wear) params.set("wear", filters.wear);
  if (filters.stattrak !== null) params.set("stattrak", String(filters.stattrak));
  if (filters.souvenir !== null) params.set("souvenir", String(filters.souvenir));
  if (filters.min_profit) params.set("min_profit", filters.min_profit);
  if (filters.min_profit_pct) params.set("min_profit_pct", filters.min_profit_pct);
  if (filters.min_liquidity) params.set("min_liquidity", filters.min_liquidity);
  for (const slug of filters.buy_site) params.append("buy_site", slug);
  for (const slug of filters.sell_site) params.append("sell_site", slug);
  for (const slug of filters.exclude_site) params.append("exclude_site", slug);
  if (filters.instant_only) params.set("instant_only", "true");
  if (filters.cash_out_only) params.set("cash_out_only", "true");
  params.set("page", String(page));
  params.set("page_size", "25");
  params.set("sort", sort);
  params.set("direction", "desc");
  return params.toString();
}
