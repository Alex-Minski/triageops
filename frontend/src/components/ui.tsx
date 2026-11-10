import type { ReactNode } from 'react';
import type { Priority, Status } from '../types';

const STATUS_LABEL: Record<Status, string> = {
  queued: 'Queued', triaging: 'Triaging', triaged: 'Auto-triaged',
  needs_review: 'Needs review', reviewed: 'Reviewed', failed: 'Failed',
};

export function StatusBadge({ status }: { status: Status }) {
  return <span className={`badge status-${status}`}>{STATUS_LABEL[status] ?? status}</span>;
}

export function PriorityBadge({ priority }: { priority?: Priority }) {
  if (!priority) return <span className="muted">—</span>;
  return <span className={`badge prio prio-${priority}`}>{priority}</span>;
}

export function Confidence({ value }: { value?: number }) {
  if (value === undefined) return <span className="muted">—</span>;
  const pct = Math.round(value * 100);
  return (
    <span className="confidence" title={`Model confidence ${pct}%`}>
      <span className="confidence-track"><span className={`confidence-fill ${value < 0.7 ? 'low' : ''}`} style={{ width: `${pct}%` }} /></span>
      <span className="num">{pct}%</span>
    </span>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/** Horizontal bars for a small categorical breakdown. */
export function Bars({ data, order }: { data: Partial<Record<string, number>>; order: string[] }) {
  const max = Math.max(1, ...order.map((k) => data[k] ?? 0));
  return (
    <div className="bars">
      {order.map((k) => (
        <div className="bar-row" key={k}>
          <span className="bar-label">{k.replace('_', ' ')}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${((data[k] ?? 0) / max) * 100}%` }} /></span>
          <span className="num">{data[k] ?? 0}</span>
        </div>
      ))}
    </div>
  );
}

/** Daily ticket volume as columns, last 14 days. */
export function Columns({ data }: { data: { date: string; count: number }[] }) {
  const max = Math.max(1, ...data.map((d) => d.count));
  const w = 560, h = 140, gap = 6, bw = (w - gap * (data.length - 1)) / data.length;
  return (
    <svg viewBox={`0 0 ${w} ${h + 22}`} className="columns" role="img" aria-label="Tickets per day, last 14 days">
      {data.map((d, i) => {
        const bh = (d.count / max) * h;
        const x = i * (bw + gap);
        return (
          <g key={d.date}>
            <title>{`${d.date}: ${d.count} tickets`}</title>
            <rect x={x} y={h - bh} width={bw} height={Math.max(bh, 1)} rx={3} className={i === data.length - 1 ? 'col today' : 'col'} />
            {(i % 2 === 1 || i === data.length - 1) && (
              <text x={x + bw / 2} y={h + 16} textAnchor="middle" className="col-label">{d.date.slice(5)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

export function timeAgo(iso: string): string {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`);
export const secs = (ms: number | null | undefined) => (ms === null || ms === undefined ? '—' : `${(ms / 1000).toFixed(1)} s`);
export const usd = (v: number | null | undefined, digits = 2) => (v === null || v === undefined ? '—' : `$${v.toFixed(digits)}`);
