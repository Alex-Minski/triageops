import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api';
import { Confidence, PriorityBadge, StatusBadge, timeAgo } from '../components/ui';
import type { Status, Ticket } from '../types';

const TABS: { status: Status; label: string }[] = [
  { status: 'needs_review', label: 'Needs review' },
  { status: 'triaged', label: 'Auto-triaged' },
  { status: 'reviewed', label: 'Reviewed' },
  { status: 'triaging', label: 'In progress' },
  { status: 'failed', label: 'Failed' },
];

const REASON: Record<string, string> = {
  low_confidence: 'Low confidence',
  possible_prompt_injection: 'Possible prompt injection',
  invalid_model_output: 'Invalid model output',
};

export default function Tickets({ fixedStatus }: { fixedStatus?: Status }) {
  const [params, setParams] = useSearchParams();
  const status = fixedStatus ?? ((params.get('status') as Status) || 'triaged');
  const [items, setItems] = useState<Ticket[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItems(null);
    api.listTickets(status).then((r) => setItems(r.items)).catch((e) => setError(e.message));
  }, [status]);

  return (
    <>
      <header className="page-head">
        <div>
          <h1>{fixedStatus ? 'Review queue' : 'Tickets'}</h1>
          <p className="muted">
            {fixedStatus
              ? 'Tickets the model was unsure about, or that tried to steer it. Your corrections grow the evaluation set.'
              : 'Every ticket, newest first.'}
          </p>
        </div>
      </header>

      {!fixedStatus && (
        <nav className="tabs">
          {TABS.map((t) => (
            <button key={t.status} className={t.status === status ? 'tab active' : 'tab'} onClick={() => setParams({ status: t.status })}>
              {t.label}
            </button>
          ))}
        </nav>
      )}

      {error && <div className="error">{error}</div>}
      {!items && !error && <div className="muted">Loading…</div>}
      {items && items.length === 0 && <div className="card empty">Nothing here.</div>}
      {items && items.length > 0 && (
        <div className="card table-card">
          <table>
            <thead>
              <tr><th>Ticket</th><th>Category</th><th>Priority</th><th>Confidence</th><th>Status</th><th>Received</th></tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const final = t.review ?? t.triage;
                return (
                  <tr key={t.ticketId}>
                    <td>
                      <Link to={`/tickets/${t.ticketId}`} className="ticket-title">{t.title}</Link>
                      <div className="row-meta">
                        <span className="mono">{t.ticketId.slice(0, 9)}</span>
                        {t.source === 'alert' && <span className="pill">alert</span>}
                        {t.duplicateOf && <span className="pill">duplicate</span>}
                        {(t.reviewReasons ?? []).map((r) => <span className="pill warn" key={r}>{REASON[r] ?? r}</span>)}
                      </div>
                    </td>
                    <td className="cap">{final?.category ?? '—'}</td>
                    <td><PriorityBadge priority={final?.priority} /></td>
                    <td><Confidence value={t.triage?.confidence} /></td>
                    <td><StatusBadge status={t.status} /></td>
                    <td className="muted nowrap">{timeAgo(t.createdAt)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
