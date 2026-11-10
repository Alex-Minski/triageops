import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function NewTicket() {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const { ticketId } = await api.createTicket(title, description);
      navigate(`/tickets/${ticketId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit');
      setBusy(false);
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <h1>New ticket</h1>
          <p className="muted">Submit a ticket and watch it go through masking, classification, duplicate search and drafting.</p>
        </div>
      </header>
      <form className="card form-narrow" onSubmit={submit}>
        <label>Title<input value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} required placeholder="VPN keeps disconnecting" /></label>
        <label>Description
          <textarea rows={7} value={description} maxLength={10000} onChange={(e) => setDescription(e.target.value)} required
            placeholder="What happened, who is affected, and since when?" />
        </label>
        <p className="fine">Personal details such as emails and phone numbers are masked before any model reads the ticket.</p>
        {error && <div className="error">{error}</div>}
        <button className="primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit ticket'}</button>
      </form>
    </>
  );
}
