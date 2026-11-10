import { idToken } from './auth';
import { getConfig } from './config';
import * as demo from './demo';
import type { Review, Stats, Status, Ticket } from './types';

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = await idToken();
  if (!token) throw new Error('Signed out');
  const res = await fetch(getConfig().apiUrl.replace(/\/$/, '') + path, {
    method,
    headers: { Authorization: token, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error ?? `${res.status} ${res.statusText}`);
  return data as T;
}

const isDemo = () => getConfig().demo === true;

export const api = {
  listTickets: (status: Status) =>
    isDemo() ? demo.listTickets(status) : request<{ items: Ticket[]; cursor: string | null }>('GET', `/tickets?status=${status}`),
  getTicket: (id: string) => (isDemo() ? demo.getTicket(id) : request<Ticket>('GET', `/tickets/${id}`)),
  createTicket: (title: string, description: string) =>
    isDemo() ? demo.createTicket(title, description)
      : request<{ ticketId: string; status: string }>('POST', '/tickets', { title, description, source: 'web' }),
  review: (id: string, review: Pick<Review, 'category' | 'priority' | 'team' | 'note'>) =>
    isDemo() ? demo.review(id, review)
      : request<{ ticketId: string; status: string; agreedWithModel: boolean }>('POST', `/tickets/${id}/review`, review),
  stats: () => (isDemo() ? demo.stats() : request<Stats>('GET', '/stats')),
};
