# Feedback Progress Email Workflow

Implement the reporter-facing staged progress mail contract from:

- `/docker/chummercomplete/chummer-design/products/chummer/FEEDBACK_PROGRESS_EMAIL_WORKFLOW.yaml`

Hub responsibilities:

- compose reporter mail from canonical support-case truth
- never treat merge or preview-only state as reporter-fixed
- only emit `fix_available` once Registry truth reaches the reporter channel
- include the bounded reason, implementation posture, ETA text, next owner, and next lane in `audited_decision`
- include a real download or updater route in `fix_available`

Sender contract:

- from: `Wageslave <wageslave@chummer.run>`
- reply-to: `support@chummer.run`

Decision awards:

- accepted / known-issue / needs-info: `Clad Feedbacker`
- rejected / deferred: `Denied`

Delivery contract:

- queue through EA `connector.dispatch`
- require Emailit sent receipts before the stage counts as complete
