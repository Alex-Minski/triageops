# Runbook: Suspected phishing email (not clicked)

**Category:** security · **Owner:** security_ops · **Typical priority:** P3; P2 if many users received it

## Resolution
1. Thank the user and ask them to use the Report Phishing button rather than forwarding the email.
2. Pull the message headers and URLs from the reported copy. Do not open links on a workstation.
3. Check the sender domain and URLs against threat intelligence.
4. Search all mailboxes for the same sender or subject and purge confirmed phishing messages.
5. Block the sender domain and URLs at the mail gateway and web proxy.
6. If anyone clicked or entered credentials, open a separate P2 incident for each person (see "Credentials entered on a phishing page").
