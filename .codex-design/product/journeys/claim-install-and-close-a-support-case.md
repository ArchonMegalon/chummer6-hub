# Claim install and close a support case

## Happy path

1. A user opens `/downloads`, chooses the recommended installer, and sees install help plus known-issue posture before downloading.
2. The user installs Chummer, optionally signs in, and claims the install so Devices & access reflects a known copy rather than an anonymous binary.
3. If the desktop head crashes, misbehaves, or feels wrong, the user can send a crash, bug, or lightweight feedback report without inventing a public issue first.
4. Hub records the case, release and install facts are attached, and Fleet receives only the normalized cluster or work packet needed for triage.
5. The fix is only marked as user-visible closure after the reporter's channel actually carries the repaired release.

## Failure modes

* If the user stays guest-only, the download still works, but claim, recovery, and install history stay optional rather than silently faked.
* If the claim code or linkage is lost, Hub must offer a recoverable claim path instead of requiring a new personalized installer.
* If a release is paused, revoked, or not yet promoted for the reporter's channel, the case must stay honest about "fix available" versus "fix actually reachable."
* If the report includes sensitive local evidence, diagnostics stay redacted and the public release shelf never becomes the raw support inbox.

## Owning repos

* `chummer6-hub`
* `chummer6-hub-registry`
* `chummer6-ui`
* `fleet`
