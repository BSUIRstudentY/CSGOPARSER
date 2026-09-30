export type Quote = {
  site: string;
  site_name: string;
  price_usd: number;
  listings_count: number | null;
  url: string;
};

export type MarketCard = {
  item_id: number;
  canonical_name: string;
  weapon: string;
  skin_name: string;
  wear: string | null;
  stattrak: boolean;
  souvenir: boolean;
  cheapest: Quote;
  highest: Quote;
  spread_usd: number;
  spread_pct: number;
  quotes: Quote[];
};

export type Opportunity = {
  id: number;
  item_id: number;
  canonical_name: string;
  weapon: string;
  skin_name: string;
  wear: string | null;
  stattrak: boolean;
  souvenir: boolean;
  buy_site: string;
  sell_site: string;
  buy_price_usd: number;
  sell_price_usd: number;
  cost_usd: number;
  proceeds_usd: number;
  profit_usd: number;
  profit_pct: number;
  liquidity: number;
  instant_trade: boolean;
  trade_lock_days: number;
  cash_out: boolean;
  computed_at: string;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type Filters = {
  q: string;
  weapon: string;
  wear: string;
  stattrak: boolean | null;
  souvenir: boolean | null;
  min_profit: string;
  min_profit_pct: string;
  min_liquidity: string;
  buy_site: string[];
  sell_site: string[];
  exclude_site: string[];
  instant_only: boolean;
  cash_out_only: boolean;
};

export type Site = {
  id: number;
  slug: string;
  name: string;
  base_url: string;
  currency: string;
  buy_fee_pct: number;
  sell_fee_pct: number;
  deposit_fee_pct: number;
  deposit_fee_flat: number;
  withdraw_fee_pct: number;
  withdraw_fee_flat: number;
  trade_lock_days: number;
  cash_out: boolean;
  enabled: boolean;
  tos_restricted: boolean;
  payment_methods: string[];
  config: Record<string, unknown>;
  secret_env: string | null;
  secret_configured: boolean;
  notes: string | null;
};

export type PricePoint = {
  site: string;
  price: number;
  price_usd: number;
  currency: string;
  listings_count: number | null;
  volume_24h: number | null;
  captured_at: string;
};

export type Item = {
  id: number;
  game: string;
  weapon: string;
  skin_name: string;
  wear: string | null;
  stattrak: boolean;
  souvenir: boolean;
  canonical_name: string;
};

export type ParserRun = {
  id: number;
  site: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  items_fetched: number;
  items_upserted: number;
  error: string | null;
};

export type Stats = {
  items: number;
  opportunities: number;
  best_profit_usd: number | null;
  best_profit_pct: number | null;
  parser_mode: string;
  sites_enabled: number;
  last_runs: ParserRun[];
};

export type SavedSearch = {
  id: number;
  name: string;
  filters: Partial<Filters>;
  created_at: string | null;
};

export type Alert = {
  id: number;
  name: string;
  filters: Partial<Filters>;
  channel: string;
  enabled: boolean;
  created_at: string | null;
  delivery: string;
};

export type User = {
  id: number;
  email: string;
  is_admin: boolean;
};

export const emptyFilters = (): Filters => ({
  q: "",
  weapon: "",
  wear: "",
  stattrak: null,
  souvenir: null,
  min_profit: "",
  min_profit_pct: "",
  min_liquidity: "",
  buy_site: [],
  sell_site: [],
  exclude_site: [],
  instant_only: false,
  cash_out_only: false,
});

export function coerceFilters(raw: object | null | undefined): Filters {
  const source = (raw ?? {}) as Record<string, unknown>;
  const base = emptyFilters();
  const text = (key: string) => {
    const value = source[key];
    return value == null || value === "" ? "" : String(value);
  };
  const list = (key: string) => (Array.isArray(source[key]) ? source[key].map(String) : base[key as "buy_site"]);
  return {
    ...base,
    q: text("q"),
    weapon: text("weapon"),
    wear: text("wear"),
    stattrak: typeof source.stattrak === "boolean" ? source.stattrak : null,
    souvenir: typeof source.souvenir === "boolean" ? source.souvenir : null,
    min_profit: text("min_profit"),
    min_profit_pct: text("min_profit_pct"),
    min_liquidity: text("min_liquidity"),
    buy_site: list("buy_site"),
    sell_site: list("sell_site"),
    exclude_site: list("exclude_site"),
    instant_only: Boolean(source.instant_only),
    cash_out_only: Boolean(source.cash_out_only),
  };
}

export function filtersPayload(filters: Filters) {
  const numberOrNull = (value: string) => (value === "" ? null : Number(value));
  return {
    ...filters,
    min_profit: numberOrNull(filters.min_profit),
    min_profit_pct: numberOrNull(filters.min_profit_pct),
    min_liquidity: numberOrNull(filters.min_liquidity),
  };
}

export function usd(value: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

export function pct(value: number): string {
  return `${value.toFixed(2)}%`;
}
