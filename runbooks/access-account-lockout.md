# Runbook: Account lockout

**Category:** access · **Owner:** identity · **Typical priority:** P2 (one user blocked)

## Symptoms
- "Your account has been locked" or "account is disabled" at sign-in.
- Repeated failed sign-ins after a recent password change.

## Resolution
1. Verify the caller's identity with the standard two-factor identity check before changing anything.
2. In the identity admin console, check the account's lockout status and the source of recent failed sign-ins.
3. If failures come from an old device (phone mail app, mapped drive, saved credentials), ask the user to remove the saved password on that device first.
4. Unlock the account. Do not reset the password unless the user asks or the failures came from an unknown location.
5. If failures came from an unknown country or IP, do NOT unlock: escalate to security_ops as a possible credential attack (see "Suspicious sign-in").
6. Confirm the user can sign in, then close the ticket.

## Escalate when
- Lockouts recur more than twice in 24 hours.
- Sign-in failures come from unfamiliar locations.
