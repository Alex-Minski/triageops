# Runbook: Wi-Fi drops, no internet, slow network

**Category:** network · **Owner:** network_ops · **Typical priority:** P3 for one user; P1 for a site-wide outage

## Resolution
1. Ask how many people are affected and where. Several users in one area points to an access point.
2. Single user: forget and rejoin the corporate network, then update the wireless driver.
3. Meeting room drops: check that room's access point in the wireless controller for errors or high client counts.
4. Wired with no internet: test another port and cable, and check that the switch port is enabled.
5. Slow everywhere: check WAN link utilisation on the network dashboard and the ISP status page.
6. Site-wide outage: declare a P1, notify the site lead, and post updates every 30 minutes.
