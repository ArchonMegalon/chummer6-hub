# Registry reads through the packaged Hub host

This small executable uses `WebApplicationFactory<HubIdentityClient>` to run the
entry point of **Chummer.Run.Api**, including its actual Program, MVC application
parts, routing, policies, middleware, DI, Registry packages and durable stores.
The generic marker is a public type in the Hub assembly; it is not a test host.
No principal is injected. Only upstream identity responses are synthetic.
Other HTTP client transports throw before sending; the real background services
remain registered, with route warmup disabled and local temporary storage.

Use only the fixed Registry package/lock supplied by the package lane. The
verifier refuses compatibility source builds and refuses to start a Registry
assembly lacking `RegistryReadAccess`. That guard is not provenance validation;
the controller must first verify the selected package version and bytes.

After the controller integrates the fixed package defaults/locks, restore this
new project once with `RestoreLockedMode=false` to create its new lock, then
build it in the serialized build slot with SDK **10.0.103** and the same pinned
Core bundle/feed as the packaged Hub. Do not update another project's lock as
part of that restore. Subsequent restores use the generated lock.

Run the built executable in its own empty-environment process:

```sh
bash tests/RegistryHostIntegration/run-isolated.sh \
  /absolute/path/to/sdk/dotnet \
  /absolute/path/to/RegistryHostIntegration.dll
```

The wrapper makes a private temporary root and removes it after host shutdown.
It does not build, restore, contact live identity, or use real accounts. The
checks cover anonymous public reads; bearer and cookie ownership; all artifact
read aliases, pagination/counts and shelf filters; publication reads; unrelated,
invalid, revoked, unlinked and unavailable identity sessions; forged owner
headers; subject/account and service/account collisions; and unchanged control
authorization for drafts, runtime/pipeline reads and CRUD writes.

Source preparation alone is not a passing HTTP integration result. Record the
exact restored package inputs, build outcome and execution outcome separately.
