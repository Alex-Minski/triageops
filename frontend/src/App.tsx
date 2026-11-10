import { useEffect, useState } from 'react';
import { NavLink, Route, Routes } from 'react-router-dom';
import { currentEmail, idToken, signOut } from './auth';
import { getConfig } from './config';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import NewTicket from './pages/NewTicket';
import TicketDetail from './pages/TicketDetail';
import Tickets from './pages/Tickets';

export default function App() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);

  useEffect(() => {
    idToken().then((t) => setSignedIn(Boolean(t)));
  }, []);

  if (signedIn === null) return null;
  if (!signedIn) return <Login onSignedIn={() => setSignedIn(true)} />;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark" />TriageOps</div>
        <nav>
          <NavLink to="/" end>Overview</NavLink>
          <NavLink to="/review">Review queue</NavLink>
          <NavLink to="/tickets">All tickets</NavLink>
          <NavLink to="/new">New ticket</NavLink>
        </nav>
        <div className="sidebar-foot">
          {getConfig().demo && <div className="demo-flag">Demo mode: sample data, not measured results</div>}
          <div className="small muted">{currentEmail()}</div>
          {!getConfig().demo && <button className="link" onClick={() => { signOut(); setSignedIn(false); }}>Sign out</button>}
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/review" element={<Tickets fixedStatus="needs_review" />} />
          <Route path="/tickets" element={<Tickets />} />
          <Route path="/tickets/:ticketId" element={<TicketDetail />} />
          <Route path="/new" element={<NewTicket />} />
        </Routes>
      </main>
    </div>
  );
}
