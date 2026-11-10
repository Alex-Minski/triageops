export type Status = 'queued' | 'triaging' | 'triaged' | 'needs_review' | 'reviewed' | 'failed';
export type Category = 'access' | 'hardware' | 'software' | 'network' | 'email' | 'security';
export type Priority = 'P1' | 'P2' | 'P3' | 'P4';
export type Team = 'service_desk' | 'desktop_support' | 'network_ops' | 'security_ops' | 'identity' | 'applications';

export const CATEGORIES: Category[] = ['access', 'hardware', 'software', 'network', 'email', 'security'];
export const PRIORITIES: Priority[] = ['P1', 'P2', 'P3', 'P4'];
export const TEAMS: Team[] = ['service_desk', 'desktop_support', 'network_ops', 'security_ops', 'identity', 'applications'];

export interface Triage {
  category?: Category;
  priority?: Priority;
  team?: Team;
  confidence?: number;
  rationale?: string;
  modelId?: string;
  costUsd?: number | null;
  latencyMs?: number;
  parseError?: string;
}

export interface Review {
  category: Category;
  priority: Priority;
  team: Team;
  note?: string;
  reviewer?: string;
  reviewedAt?: string;
  agreedWithModel?: boolean;
}

export interface Neighbour { ticketId: string; title: string; category: string; similarity: number }

export interface Draft {
  text?: string;
  citations?: string[];
  retrieved?: { source: string; score: number }[];
  skipped?: boolean;
  modelId?: string;
  costUsd?: number | null;
}

export interface Ticket {
  ticketId: string;
  status: Status;
  source: 'web' | 'email' | 'alert';
  title: string;
  description?: string;
  createdAt: string;
  triagedAt?: string;
  triage?: Triage;
  review?: Review;
  reviewReasons?: string[];
  duplicates?: Neighbour[];
  duplicateOf?: string | null;
  draft?: Draft;
  piiTypes?: string[];
  promptAttack?: boolean;
  costUsd?: number;
  e2eLatencyMs?: number;
  error?: { type: string; cause: string };
}

export interface Stats {
  total: number;
  byStatus: Partial<Record<Status, number>>;
  byCategory: Partial<Record<Category, number>>;
  byPriority: Partial<Record<Priority, number>>;
  autoTriageRate: number | null;
  reviewAgreementRate: number | null;
  reviewedCount: number;
  costUsd: { total: number; perTicket: number | null; per1000Tickets: number | null };
  latencyMs: { p50: number | null; p95: number | null };
  recurring: { ticketId: string; title: string; duplicates: number }[];
  daily: { date: string; count: number }[];
}
