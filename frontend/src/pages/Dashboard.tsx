import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { Bars, Columns, Stat, pct, secs, usd } from '../components/ui';
import { CATEGORIES, PRIORITIES, type Stats } from '../types';

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.stats().then(setStats).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error">{error}</div>;
  if (!stats) return <div className="muted">Loading…</div>;
  const waiting = stats.byStatus.needs_review ?? 0;

  return (
    <>
      <header className="page-head">
        <div>
          <h1>Overview</h1>
          <p className="muted">{stats.total} tickets triaged by the Bedrock pipeline</p>
        </div>
        {waiting > 0 && <Link className="button primary" to="/review">Review {waiting} waiting</Link>}
      </header>

      <section className="stats">
        <Stat label="Auto-triaged" value={pct(stats.autoTriageRate)} hint="confidence above the review threshold" />
        <Stat label="Reviewer agreed" value={pct(stats.reviewAgreementRate)} hint={`of ${stats.reviewedCount} human reviews`} />
        <Stat label="Cost per 1,000 tickets" value={usd(stats.costUsd.per1000Tickets)} hint="estimated Bedrock spend" />
        <Stat label="End-to-end latency" value={secs(stats.latencyMs.p50)} hint={`p95 ${secs(stats.latencyMs.p95)}`} />
      </section>

      <section className="grid-2">
        <div className="card">
          <h2>Tickets per day</h2>
          <Columns data={stats.daily} />
        </div>
        <div className="card">
          <h2>Recurring issues</h2>
          {stats.recurring.length === 0 ? (
            <p className="muted">No duplicate clusters yet.</p>
          ) : (
            <ol className="recurring">
              {stats.recurring.map((r) => (
                <li key={r.ticketId}>
                  <Link to={`/tickets/${r.ticketId}`}>{r.title || r.ticketId}</Link>
                  <span className="pill">+{r.duplicates} similar</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>

      <section className="grid-2">
        <div className="card"><h2>By category</h2><Bars data={stats.byCategory} order={CATEGORIES} /></div>
        <div className="card"><h2>By priority</h2><Bars data={stats.byPriority} order={PRIORITIES} /></div>
      </section>
    </>
  );
}
