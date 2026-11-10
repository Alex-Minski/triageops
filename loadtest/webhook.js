// k6 load test for the alert webhook.
//
//   k6 run -e API_URL=<ApiUrl from outputs> -e API_KEY=<webhook key> -e RATE=60 loadtest/webhook.js
//
// RATE is alerts per minute held for DURATION. Afterwards, check that every
// ticket was triaged and the dead-letter queue stayed empty:
//   python scripts/check_run.py --since <start time printed below>
// Start low (60/min) and step up; Bedrock quotas, not Lambda, are the limit.
// Each alert costs a little Bedrock money: 1,000 alerts on Nova Lite is cents, not dollars.

import http from 'k6/http';
import { check } from 'k6';

const RATE = Number(__ENV.RATE || 60);
const DURATION = __ENV.DURATION || '5m';

export const options = {
  scenarios: {
    alerts: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1m',
      duration: DURATION,
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800'],
  },
};

const TITLES = [
  ['Defender detected threat', 'Trojan quarantined on laptop. Alert severity: high'],
  ['Suspicious sign-in', 'Impossible travel: sign-ins from two countries within 20 minutes'],
  ['VPN gateway unreachable', 'Several users report GlobalProtect gateway not responding'],
  ['Printer offline', 'Third floor printer offline for all users'],
  ['Outlook not syncing', 'User mailbox has not synced since yesterday'],
];

export function setup() {
  console.log(`load test start (UTC): ${new Date().toISOString()}`);
}

export default function () {
  const [title, description] = TITLES[Math.floor(Math.random() * TITLES.length)];
  const body = JSON.stringify({
    alertId: `load-${__VU}-${__ITER}-${Date.now()}`,
    title,
    description,
    severity: 'medium',
  });
  const res = http.post(`${__ENV.API_URL.replace(/\/$/, '')}/webhooks/alerts`, body, {
    headers: { 'Content-Type': 'application/json', 'x-api-key': __ENV.API_KEY },
  });
  check(res, { 'accepted (202)': (r) => r.status === 202 });
}
