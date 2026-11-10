# Runbook: Internal sites unreachable, DNS problems

**Category:** network · **Owner:** network_ops · **Typical priority:** P2

## Resolution
1. Test whether the site resolves: `nslookup intranet.corp.local`. A failure points to DNS.
2. If the user is remote, confirm the VPN is connected: internal names resolve only over the VPN.
3. Flush the local DNS cache (`ipconfig /flushdns`) and retry.
4. If the name resolves but the site times out, the problem is the site or a firewall rule. Escalate to the site's owner.
5. If several users are affected, check the health of the internal DNS servers and recent DNS changes.
