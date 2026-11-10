# Runbook: Outlook not syncing, mail stuck in outbox, not receiving mail

**Category:** email · **Owner:** applications · **Typical priority:** P2 if the user can't send or receive at all

## Resolution
1. Check the mail service health dashboard for an active incident.
2. Ask the user to check webmail. If webmail works, the problem is the local Outlook profile.
3. Outlook not syncing: turn off Work Offline, then restart Outlook. If it still fails, create a new Outlook profile.
4. Stuck in outbox: look for an oversized attachment (over 25 MB) and remove it or share it as a link instead.
5. Not receiving external mail: run a message trace on a known sender and check the quarantine for false positives.
6. Mailbox full: archive old mail or raise the quota with the manager's approval.
