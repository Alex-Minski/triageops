# Runbook: Printer jams, offline printers, stuck print queue

**Category:** hardware · **Owner:** desktop_support · **Typical priority:** P3, or P2 if a whole floor cannot print

## Resolution
1. False paper jam: open every tray and door, remove scraps, and check the rear access panel.
2. Printer offline for one user: remove and re-add the printer from the print server, then restart the print spooler service.
3. Printer offline for everyone: check the printer's network cable and its IP on the display, and ping it from the print server.
4. Jobs stuck in the queue: clear the queue on the print server and restart the spooler there.
5. If hardware errors persist, place an "out of order" note and log a vendor service call with the printer's asset tag.
