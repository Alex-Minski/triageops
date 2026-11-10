# Runbook: VPN won't connect or keeps dropping

**Category:** network · **Owner:** network_ops · **Typical priority:** P2 for a remote user who is fully blocked; P1 if many users report it at once

## Resolution
1. Confirm the user's home internet works without the VPN.
2. "Gateway not responding": check the VPN gateway status dashboard. If the gateway is down, raise a P1 and link all reports to it.
3. Single user: sign out of the VPN client, choose the nearest gateway manually, and reconnect.
4. Drops every few minutes: switch the client from UDP to TLS (TCP) mode and ask the user to test on a wired connection.
5. Stuck "connecting": reinstall the VPN client from the software portal.
6. Check the user's certificate hasn't expired in the client's settings.
