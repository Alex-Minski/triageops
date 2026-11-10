# Runbook: Suspicious sign-in or unexpected MFA prompts

**Category:** security · **Owner:** security_ops · **Typical priority:** P2; P1 for privileged accounts

## Symptoms
- An MFA prompt the user didn't trigger (MFA fatigue attack).
- Sign-ins from an unfamiliar country, or "impossible travel" alerts.

## Resolution
1. Tell the user to deny every prompt they didn't start and never approve to make the prompts stop.
2. Revoke sessions and reset the password: unexpected MFA prompts mean the password is already known to someone.
3. Switch the account to number-matching MFA if it isn't already.
4. Review the sign-in logs for successful sign-ins from the suspicious IP and block it.
5. If any suspicious sign-in succeeded, follow "Credentials entered on a phishing page" from step 4.
