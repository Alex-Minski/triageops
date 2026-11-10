# Runbook: MFA codes rejected or new phone

**Category:** access · **Owner:** identity · **Typical priority:** P2

## Symptoms
- Authenticator codes are rejected.
- The user changed or lost their phone and cannot approve prompts.
- Push notifications never arrive.

## Resolution
1. Verify identity with the standard identity check. Never re-register MFA on a request that arrives only by email.
2. Codes rejected: ask the user to turn on automatic date and time on the phone; code drift is the most common cause.
3. Push not arriving: check notifications are allowed for the authenticator app and the phone has data.
4. New or lost phone: revoke the old MFA methods, issue a one-time temporary access pass, and walk the user through registering the new device.
5. Ask the user to sign out and back in on all devices once the new method works.

## Escalate when
- The user reports MFA prompts they did not trigger: that is a security incident. Follow "Suspicious sign-in".
