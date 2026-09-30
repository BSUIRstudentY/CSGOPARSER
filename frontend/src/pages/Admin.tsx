import { useEffect, useState } from "react";

import { api } from "../api";
import { useAuth } from "../auth";
import type { ParserRun, Site } from "../types";

type Alias = {
  id: number;
  site: string;
  raw_name: string;
  match_method: string;
  confidence: number;
  suggested_item_id: number | null;
};

export function AdminPage() {
  const { user } = useAuth();
  const [sites, setSites] = useState<Site[]>([]);
  const [runs, setRuns] = useState<ParserRun[]>([]);
  const [aliases, setAliases] = useState<Alias[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function reload() {
    if (!user?.is_admin) return;
    Promise.all([
      api<Site[]>("/sites"),
      api<ParserRun[]>("/admin/parser-runs"),
      api<Alias[]>("/admin/aliases?needs_review=true"),
    ])
      .then(([siteRows, runRows, aliasRows]) => {
        setSites(siteRows);
        setRuns(runRows);
        setAliases(aliasRows);
      })
      .catch((err: Error) => setError(err.message));
  }

  useEffect(() => {
    reload();
  }, [user]);

  if (!user?.is_admin) {
    return <p className="text-muted">Admin access is required to edit fees and parser runs.</p>;
  }

  async function patch(site: Site, changes: Partial<Site>) {
    const updated = await api<Site>(`/sites/${site.id}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    });
    setSites((current) => current.map((row) => (row.id === updated.id ? updated : row)));
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-medium">Marketplaces</h1>
      {error && <p className="text-sm text-loss">{error}</p>}
      {notice && <p className="text-sm text-gold">{notice}</p>}
      <div className="space-y-3">
        {sites.map((site) => (
          <article key={site.id} className="rounded border border-line bg-panel p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="font-medium">{site.name}</h2>
                <p className="text-xs text-muted">{site.base_url}</p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={site.enabled}
                  onChange={(event) => void patch(site, { enabled: event.target.checked })}
                />
                Enabled
              </label>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-4">
              <Fee
                label="Sell fee %"
                value={site.sell_fee_pct * 100}
                onCommit={(percent) => void patch(site, { sell_fee_pct: percent / 100 })}
              />
              <Fee
                label="Buy fee %"
                value={site.buy_fee_pct * 100}
                onCommit={(percent) => void patch(site, { buy_fee_pct: percent / 100 })}
              />
              <Fee
                label="Trade lock days"
                value={site.trade_lock_days}
                onCommit={(days) => void patch(site, { trade_lock_days: days })}
              />
              <label className="text-xs text-muted">
                Cash out
                <input
                  className="ml-2"
                  type="checkbox"
                  checked={site.cash_out}
                  onChange={(event) => void patch(site, { cash_out: event.target.checked })}
                />
              </label>
            </div>
            {site.notes && <p className="mt-3 text-xs leading-5 text-muted">{site.notes}</p>}
            <button
              type="button"
              className="mt-3 rounded border border-line px-3 py-1 text-sm"
              onClick={() => {
                void api(`/admin/parsers/${site.slug}/run`, { method: "POST" }).then(() => {
                  setNotice(`Parser started for ${site.name}. Refresh in a moment to see the run.`);
                });
              }}
            >
              Run parser
            </button>
          </article>
        ))}
      </div>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-muted">Recent parser runs</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {runs.map((run) => (
            <li key={run.id} className="rounded border border-line px-3 py-2">
              <span className="font-mono">{run.site}</span> · {run.status} · fetched {run.items_fetched} · wrote{" "}
              {run.items_upserted}
              {run.error && <div className="text-loss">{run.error}</div>}
            </li>
          ))}
          {runs.length === 0 && <li className="text-muted">No runs yet.</li>}
        </ul>
      </section>
      <section>
        <h2 className="text-sm uppercase tracking-wide text-muted">Names waiting for review</h2>
        <ul className="mt-2 space-y-2 text-sm">
          {aliases.map((alias) => (
            <li key={alias.id} className="rounded border border-line px-3 py-2">
              {alias.site}: {alias.raw_name} ({alias.match_method}, {(alias.confidence * 100).toFixed(0)}%)
              {alias.suggested_item_id && (
                <button
                  type="button"
                  className="ml-3 text-gold"
                  onClick={() => {
                    void api(`/admin/aliases/${alias.id}/link`, {
                      method: "POST",
                      body: JSON.stringify({ item_id: alias.suggested_item_id }),
                    }).then(reload);
                  }}
                >
                  Accept suggestion
                </button>
              )}
            </li>
          ))}
          {aliases.length === 0 && <li className="text-muted">Nothing waiting.</li>}
        </ul>
      </section>
    </div>
  );
}

function Fee({
  label,
  value,
  onCommit,
}: {
  label: string;
  value: number;
  onCommit: (next: number) => void;
}) {
  const [draft, setDraft] = useState(String(Number(value.toFixed(2))));
  useEffect(() => setDraft(String(Number(value.toFixed(2)))), [value]);
  return (
    <label className="text-xs text-muted">
      {label}
      <input
        className="mt-1 w-full rounded border border-line bg-ink px-2 py-1 text-paper"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const next = Number(draft);
          if (!Number.isNaN(next)) onCommit(next);
        }}
      />
    </label>
  );
}
