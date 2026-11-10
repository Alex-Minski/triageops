# Runbook: Business application errors (Workday, ERP, Salesforce)

**Category:** software · **Owner:** applications · **Typical priority:** P2 if a deadline such as payroll or month-end is at risk, otherwise P3

## Resolution
1. Record the exact error message, the time, and the screen or report name.
2. Check the vendor status page and the internal change calendar for an outage or recent release.
3. Ask the user to try a private browser window to rule out cached sessions.
4. If several users report the same error within an hour, raise one parent ticket and link the others to it.
5. Timeouts on reports: check whether the report's date range can be narrowed. Otherwise escalate to the application owner with the report ID.
6. Payroll and timesheet errors near a payroll deadline are always P2.
