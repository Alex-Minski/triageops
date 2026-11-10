import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { Confidence, PriorityBadge, StatusBadge, secs, timeAgo } from '../components/ui';
import { CATEGORIES, PRIORITIES, TEAMS, type Category, type Priority, type Team, type Ticket } from '../types';

const PENDING = ['queued', 'triaging'];

export default function TicketDetail() {
  const { ticketId = '' } = useParams();
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const load = useCallback(() => api.getTicket(ticketId).then(setTicket).catch((e) => setError(e.message)), [ticketId]);

  useEffect(() => { load(); }, [load]);
  // Triage is asynchronous: poll until the workflow finishes.
  useEffect(() => {
    if (!ticket || !PENDING.includes(ticket.status)) return;
    const id = setInterval(load, 2000);
    return () => clearInterval(id);
  }, [ticket, load]);

  if (error) return <div className="error">{error}</div>;
  if (!ticket) return <div className="muted">Loading…</div>;
  const tr = ticket.triage;

  return (
    <>
      <button className="link back" onClick={() => navigate(-1)}>← Back</button>
      <header className="page-head">
        <div>
          <h1>{ticket.title}</h1>
          <p className="muted">
            <span className="mono">{ticket.ticketId}</span> · {ticket.source} · received {timeAgo(ticket.createdAt)}
            {ticket.e2eLatencyMs !== undefined && <> · triaged in {secs(ticket.e2eLatencyMs)}</>}
          </p>
        </div>
        <StatusBadge status={ticket.status} />
      </header>

      {PENDING.includes(ticket.status) && <div className="card notice">Triage in progress… this page updates by itself.</div>}
      {ticket.status === 'failed' && <div className="error">Workflow failed: {ticket.error?.type} {ticket.error?.cause}</div>}

      <section className="grid-detail">
        <div className="stack">
          <div className="card">
            <h2>Ticket <span className="muted small">(as the model saw it, after PII masking)</span></h2>
            <p className="ticket-body">{ticket.description}</p>
            <div className="row-meta">
              {(ticket.piiTypes ?? []).map((p) => <span className="pill" key={p}>masked {p.toLowerCase().replace(/_/g, ' ')}</span>)}
              {ticket.promptAttack && <span className="pill warn">guardrail flagged a prompt-injection attempt</span>}
            </div>
          </div>

          {ticket.draft && !ticket.draft.skipped && ticket.draft.text && (
            <div className="card">
              <h2>Suggested fix</h2>
              <p className="draft">{ticket.draft.text}</p>
              {(ticket.draft.citations ?? []).length > 0 && (
                <div className="sources">
                  <span className="muted small">Sources</span>
                  {ticket.draft.citations!.map((c, i) => <span key={c} className="source">[{i + 1}] {c.split('/').pop()}</span>)}
                </div>
              )}
            </div>
          )}

          {(ticket.duplicates ?? []).length > 0 && (
            <div className="card">
              <h2>Similar past tickets</h2>
              <ul className="similar">
                {ticket.duplicates!.map((d) => (
                  <li key={d.ticketId}>
                    <Link to={`/tickets/${d.ticketId}`}>{d.title || d.ticketId}</Link>
                    <span className={d.ticketId === ticket.duplicateOf ? 'pill warn' : 'pill'}>{Math.round(d.similarity * 100)}% similar</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="stack">
          <div className="card">
            <h2>Model triage</h2>
            {tr?.parseError ? <p className="error">The model returned invalid output twice.</p> : tr ? (
              <dl className="facts">
                <dt>Category</dt><dd className="cap">{tr.category}</dd>
                <dt>Priority</dt><dd><PriorityBadge priority={tr.priority} /></dd>
                <dt>Team</dt><dd className="cap">{tr.team?.replace('_', ' ')}</dd>
                <dt>Confidence</dt><dd><Confidence value={tr.confidence} /></dd>
                <dt>Why</dt><dd>{tr.rationale}</dd>
                <dt>Model</dt><dd className="mono small">{tr.modelId}</dd>
                <dt>Cost</dt><dd className="small">{ticket.costUsd !== undefined ? `$${ticket.costUsd.toFixed(5)} (all steps)` : '—'}</dd>
              </dl>
            ) : <p className="muted">Not triaged yet.</p>}
          </div>
          {!PENDING.includes(ticket.status) && ticket.status !== 'failed' && <ReviewForm ticket={ticket} onDone={load} />}
        </div>
      </section>
    </>
  );
}

function ReviewForm({ ticket, onDone }: { ticket: Ticket; onDone: () => void }) {
  const base = ticket.review ?? ticket.triage;
  const [category, setCategory] = useState<Category>(base?.category ?? 'software');
  const [priority, setPriority] = useState<Priority>(base?.priority ?? 'P3');
  const [team, setTeam] = useState<Team>(base?.team ?? 'service_desk');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.review(ticket.ticketId, { category, priority, team, note: note || undefined });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Review failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>{ticket.review ? 'Your review' : 'Review'}</h2>
      {ticket.review && (
        <p className="small muted">
          {ticket.review.agreedWithModel ? 'Agreed with the model' : 'Corrected the model'} · {ticket.review.reviewer}
        </p>
      )}
      <label>Category<select value={category} onChange={(e) => setCategory(e.target.value as Category)}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></label>
      <label>Priority<select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>{PRIORITIES.map((p) => <option key={p}>{p}</option>)}</select></label>
      <label>Team<select value={team} onChange={(e) => setTeam(e.target.value as Team)}>{TEAMS.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}</select></label>
      <label><span>Note <span className="muted small">(optional)</span></span><textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
      {error && <div className="error">{error}</div>}
      <button className="primary" disabled={busy}>{busy ? 'Saving…' : ticket.review ? 'Update review' : 'Confirm triage'}</button>
    </form>
  );
}
