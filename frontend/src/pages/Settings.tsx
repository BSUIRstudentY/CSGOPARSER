import { FormEvent, useEffect, useState } from "react";

import { api } from "../api";
import type { Alert, Filters, SavedSearch } from "../types";
import { coerceFilters, emptyFilters, filtersPayload } from "../types";

export function SettingsPage() {
  const [filters, setFilters] = useState<Filters>(emptyFilters());
  const [searches, setSearches] = useState<SavedSearch[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [name, setName] = useState("My filter");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    Promise.all([
      api<{ default_filters: Partial<Filters> }>("/settings"),
      api<SavedSearch[]>("/saved-searches"),
      api<Alert[]>("/alerts"),
    ])
      .then(([settings, saved, alertRows]) => {
        setFilters(coerceFilters(settings.default_filters));
        setSearches(saved);
        setAlerts(alertRows);
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    reload();
  }, []);

  async function saveDefaults(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    try {
      await api("/settings", {
        method: "PUT",
        body: JSON.stringify({ default_filters: filtersPayload(filters) }),
      });
      setMessage("Default filters saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  async function saveSearch() {
    await api("/saved-searches", {
      method: "POST",
      body: JSON.stringify({ name, filters: filtersPayload(filters) }),
    });
    reload();
  }

  async function createAlert() {
    await api("/alerts", {
      method: "POST",
      body: JSON.stringify({ name, filters: filtersPayload(filters), channel: "telegram", enabled: true }),
    });
    setMessage("Alert stored. Delivery to Telegram or Discord is not wired up yet.");
    reload();
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-medium">Settings</h1>
      {error && <p className="text-sm text-loss">{error}</p>}
      {message && <p className="text-sm text-gain">{message}</p>}
      <form onSubmit={saveDefaults} className="space-y-3 rounded border border-line bg-panel p-4">
        <h2 className="text-sm uppercase tracking-wide text-muted">Default filters</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            Min profit %
            <input
              className="mt-1 w-full rounded border border-line bg-ink px-3 py-2"
              value={filters.min_profit_pct}
              onChange={(event) => setFilters({ ...filters, min_profit_pct: event.target.value })}
            />
          </label>
          <label className="text-sm">
            Min profit $
            <input
              className="mt-1 w-full rounded border border-line bg-ink px-3 py-2"
              value={filters.min_profit}
              onChange={(event) => setFilters({ ...filters, min_profit: event.target.value })}
            />
          </label>
          <label className="text-sm">
            Min listings
            <input
              className="mt-1 w-full rounded border border-line bg-ink px-3 py-2"
              value={filters.min_liquidity}
              onChange={(event) => setFilters({ ...filters, min_liquidity: event.target.value })}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.instant_only}
            onChange={(event) => setFilters({ ...filters, instant_only: event.target.checked })}
          />
          Instant trade only
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.cash_out_only}
            onChange={(event) => setFilters({ ...filters, cash_out_only: event.target.checked })}
          />
          Cash-out marketplaces only
        </label>
        <button type="submit" className="rounded bg-gold px-3 py-2 text-sm font-medium text-ink">
          Save defaults
        </button>
      </form>
      <section className="rounded border border-line bg-panel p-4">
        <h2 className="text-sm uppercase tracking-wide text-muted">Saved searches and alerts</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            className="rounded border border-line bg-ink px-3 py-2"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button type="button" className="rounded border border-line px-3 py-2 text-sm" onClick={() => void saveSearch()}>
            Save search
          </button>
          <button type="button" className="rounded border border-line px-3 py-2 text-sm" onClick={() => void createAlert()}>
            Store alert
          </button>
        </div>
        <ul className="mt-4 space-y-2 text-sm">
          {searches.map((search) => (
            <li key={search.id} className="flex items-center justify-between border-t border-line pt-2">
              <span>{search.name}</span>
              <button
                type="button"
                className="text-muted hover:text-loss"
                onClick={() => {
                  void api(`/saved-searches/${search.id}`, { method: "DELETE" }).then(reload);
                }}
              >
                Delete
              </button>
            </li>
          ))}
          {alerts.map((alert) => (
            <li key={`a-${alert.id}`} className="flex items-center justify-between border-t border-line pt-2">
              <span>
                {alert.name} · {alert.channel} · stored only
              </span>
              <button
                type="button"
                className="text-muted hover:text-loss"
                onClick={() => {
                  void api(`/alerts/${alert.id}`, { method: "DELETE" }).then(reload);
                }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
