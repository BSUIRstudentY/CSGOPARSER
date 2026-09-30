import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "../api";
import type { MarketCard, PricePoint } from "../types";
import { pct, usd } from "../types";

const COLORS = ["#e0b15a", "#6cb6ff", "#3dd68c", "#c3c7ce", "#d2a8ff"];

export function ItemPage() {
  const params = useParams();
  const itemId = params.itemId ?? "";
  const [card, setCard] = useState<MarketCard | null>(null);
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!itemId) return;
    Promise.all([
      api<MarketCard>(`/market/${itemId}`),
      api<PricePoint[]>(`/items/${itemId}/prices?hours=336`),
    ])
      .then(([comparison, history]) => {
        setCard(comparison);
        setPrices(history);
      })
      .catch((err: Error) => setError(err.message));
  }, [itemId]);

  const chart = useMemo(() => {
    const names = new Map(card?.quotes.map((quote) => [quote.site, quote.site_name]) ?? []);
    return buildChart(prices, names);
  }, [prices, card]);

  if (error) return <p className="text-loss">{error}</p>;
  if (!card) return <p className="text-muted">Загрузка скина…</p>;

  return (
    <div className="space-y-4">
      <Link to="/" className="text-sm text-muted hover:text-paper">
        Назад в маркет
      </Link>
      <header>
        <h1 className="text-2xl font-medium">{card.canonical_name}</h1>
        <p className="mt-1 text-sm text-muted">
          {card.weapon}
          {card.wear ? ` · ${card.wear}` : ""}
          {card.stattrak ? " · StatTrak" : ""}
          {card.souvenir ? " · Souvenir" : ""}
          {` · разница ${usd(card.spread_usd)} (${pct(card.spread_pct)})`}
        </p>
      </header>
      <section className="h-72 rounded border border-line bg-panel p-3">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chart.rows}>
            <CartesianGrid stroke="#2c3544" />
            <XAxis dataKey="time" hide />
            <YAxis stroke="#8b97a8" width={60} />
            <Tooltip
              contentStyle={{ background: "#151a22", border: "1px solid #2c3544" }}
              formatter={(value) => usd(Number(value))}
            />
            <Legend />
            {chart.sites.map((site, index) => (
              <Line
                key={site}
                type="monotone"
                dataKey={site}
                stroke={COLORS[index % COLORS.length]}
                dot={false}
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </section>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {card?.quotes.map((quote) => (
          <a
            key={quote.site}
            href={quote.url}
            target="_blank"
            rel="noreferrer"
            className="rounded border border-line bg-panel p-3 hover:border-gold"
          >
            <div className="text-xs uppercase text-muted">{quote.site_name}</div>
            <div className="mt-1 font-mono text-lg">{usd(quote.price_usd)}</div>
            <div className="text-xs text-muted">{quote.listings_count ?? "—"} лотов</div>
            <div className="mt-2 text-sm text-gold">Открыть на площадке</div>
          </a>
        ))}
      </section>
    </div>
  );
}

function buildChart(
  points: PricePoint[],
  names: Map<string, string>,
): { sites: string[]; rows: Array<Record<string, string | number>> } {
  const sites = [...new Set(points.map((point) => names.get(point.site) ?? point.site))];
  const grouped = new Map<string, Record<string, string | number>>();
  for (const point of points) {
    const stamp = new Date(point.captured_at).toLocaleString();
    const row = grouped.get(stamp) ?? { time: stamp };
    row[names.get(point.site) ?? point.site] = point.price_usd;
    grouped.set(stamp, row);
  }
  return { sites, rows: [...grouped.values()] };
}
