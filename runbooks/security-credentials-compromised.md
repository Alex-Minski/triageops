# Runbook: Credentials entered on a phishing page, or a malicious attachment opened

**Category:** security · **Owner:** security_ops · **Typical priority:** P2 for one user; P1 if several accounts are affected or an admin account is involved

## Resolution
1. Act immediately. Revoke all of the user's active sessions and refresh tokens.
2. Force a password reset and re-register MFA after verifying identity out of band (by phone, never by email).
3. If an attachment was opened, isolate the device from the network with the endpoint security console.
4. Review the account's sign-ins and mailbox rules for the last 7 days. Attackers often add forwarding rules.
5. Check for consent grants to unknown applications and remove them.
6. Run a full endpoint scan, then re-image the device if anything is found.
7. Document the timeline for the incident report.
