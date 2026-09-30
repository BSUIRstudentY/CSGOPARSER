import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import type { MarketCard, Page, Stats } from "../types";
import { pct, usd } from "../types";

export function DashboardPage() {
  const [q, setQ] = useState("");
  const [weapon, setWeapon] = useState("");
  const [wear, setWear] = useState("");
  const [minSpread, setMinSpread] = useState("");
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<Page<MarketCard> | null>(null);
  const [weapons, setWeapons] = useState<string[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api<{ weapons: string[] }>("/items/facets"), api<Stats>("/stats")])
      .then(([facets, statsRow]) => {
        setWeapons(facets.weapons);
        setStats(statsRow);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  useEffect(() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (weapon) params.set("weapon", weapon);
    if (wear) params.set("wear", wear);
    if (minSpread) params.set("min_spread", minSpread);
    params.set("page", String(page));
    params.set("page_size", "24");
    const handle = window.setTimeout(() => {
      setLoading(true);
      api<Page<MarketCard>>(`/market?${params.toString()}`)
        .then((result) => {
          setRows(result);
          setError(null);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setLoading(false));
    }, 200);
    return () => window.clearTimeout(handle);
  }, [q, weapon, wear, minSpread, page]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-medium">Маркет</h1>
        <p className="mt-1 text-sm text-muted">
          Один и тот же скин на разных площадках. Сравниваем спрос: лучшую заявку на покупку, а не
          самый дешёвый лот. Сверху те, у кого заявки расходятся сильнее.
        </p>
        <p className="mt-1 text-sm text-muted">
          Skinport и Steam не отдают общий список заявок. DMarket отдаёт спрос только с ключами
          API, поэтому их нет в сравнении, пока заявка не записана.
        </p>
      </div>
      <section className="grid gap-3 sm:grid-cols-3">
        <Stat label="Скинов в базе" value={stats ? String(stats.items) : "—"} />
        <Stat label="В этой выборке" value={rows ? String(rows.total) : "—"} />
        <Stat
          label="Крупнейшая разница"
          value={rows?.items[0] ? usd(rows.items[0].spread_usd) : "—"}
          hint={rows?.items[0] ? pct(rows.items[0].spread_pct) : undefined}
        />
      </section>
      {stats?.parser_mode === "demo" && (
        <p className="rounded border border-gold/40 bg-gold/10 px-3 py-2 text-sm text-gold">
          Сейчас показаны демо-цены. PARSER_MODE=live подключает живые площадки.
        </p>
      )}
      <section className="grid gap-3 rounded border border-line bg-panel p-3 md:grid-cols-4">
        <Field label="Скин">
          <input
            className="field"
            value={q}
            onChange={(event) => {
              setPage(1);
              setQ(event.target.value);
            }}
            placeholder="Asiimov, Doppler…"
          />
        </Field>
        <Field label="Оружие">
          <select
            className="field"
            value={weapon}
            onChange={(event) => {
              setPage(1);
              setWeapon(event.target.value);
            }}
          >
            <option value="">Любое</option>
            {weapons.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Износ">
          <select
            className="field"
            value={wear}
            onChange={(event) => {
              setPage(1);
              setWear(event.target.value);
            }}
          >
            <option value="">Любой</option>
            {["FN", "MW", "FT", "WW", "BS"].map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Мин. разница, $">
          <input
            className="field"
            value={minSpread}
            inputMode="decimal"
            onChange={(event) => {
              setPage(1);
              setMinSpread(event.target.value);
            }}
          />
        </Field>
      </section>
      {error && <p className="text-sm text-loss">{error}</p>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {rows?.items.map((card) => (
          <Link
            key={card.item_id}
            to={`/items/${card.item_id}`}
            className="rounded border border-line bg-panel p-4 hover:border-gold"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-sm font-medium leading-5">{card.canonical_name}</h2>
              <div className="shrink-0 text-right">
                <div className="font-mono text-gain">{usd(card.spread_usd)}</div>
                <div className="text-xs text-muted">{pct(card.spread_pct)}</div>
              </div>
            </div>
            <p className="mt-3 text-sm text-muted">
              от <span className="font-mono text-paper">{usd(card.cheapest.price_usd)}</span> на{" "}
              {card.cheapest.site_name} до{" "}
              <span className="font-mono text-paper">{usd(card.highest.price_usd)}</span> на{" "}
              {card.highest.site_name}
            </p>
            <ul className="mt-3 space-y-1 text-xs text-muted">
              {card.quotes.map((quote) => (
                <li key={quote.site} className="flex justify-between gap-3 font-mono">
                  <span>{quote.site_name}</span>
                  <span className="text-paper">{usd(quote.price_usd)}</span>
                </li>
              ))}
            </ul>
          </Link>
        ))}
      </div>
      {!loading && rows && rows.items.length === 0 && (
        <p className="rounded border border-line px-3 py-8 text-center text-sm text-muted">
          Нет скинов со спросом хотя бы на двух площадках.
        </p>
      )}
      <div className="flex items-center justify-between text-sm text-muted">
        <span>{loading ? "Загрузка…" : `${rows?.total ?? 0} скинов`}</span>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-line px-3 py-1 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((current) => current - 1)}
          >
            Назад
          </button>
          <button
            type="button"
            className="rounded border border-line px-3 py-1 disabled:opacity-40"
            disabled={!rows || page * rows.page_size >= rows.total}
            onClick={() => setPage((current) => current + 1)}
          >
            Дальше
          </button>
        </div>
      </div>
      <style>{`
        .field { width: 100%; border-radius: 0.25rem; border: 1px solid #2c3544; background: #0c0f14; padding: 0.4rem 0.6rem; }
      `}</style>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border border-line bg-panel px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 font-mono text-xl">
        {value} {hint && <span className="text-sm text-gain">{hint}</span>}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-xs uppercase tracking-wide text-muted">
      {label}
      <div className="mt-1 normal-case tracking-normal text-paper">{children}</div>
    </label>
  );
}
