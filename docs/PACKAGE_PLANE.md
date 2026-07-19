# Hub package plane

Hub consumes external Core and Registry assemblies from the immutable source
lock in `eng/package-plane.lock.json`. The default build graph does not inspect
or prefer sibling repositories, even when they happen to exist.

Build a fresh feed from the locked owner commits:

```bash
feed_parent="$(mktemp -d)"
python3 scripts/ai/bootstrap-hub-package-feed.py \
  --repo-root . \
  --feed "$feed_parent/feed"
```

Point normal builds at that feed with `CHUMMER_PACKAGE_FEED` or the MSBuild
property `ChummerPackageFeed`. The authority lock records one version per
owner package: Engine Contracts `5.225.0`, Registry Contracts
`0.1.0-preview`, and Registry runtime `0.1.0-preview`. Hub contracts use their
independent `ChummerPackagePlaneVersion` (`0.1.0-preview`). Integration lanes
may explicitly pin the same values through
`ChummerEngineContractsPackageVersion`,
`ChummerHubRegistryContractsPackageVersion`, and
`ChummerRunRegistryPackageVersion`; Hub's own `PackageVersion` is never
coupled to an owner dependency version.

Run the clean-checkout/no-siblings proof after committing the candidate:

```bash
python3 scripts/ai/verify-hub-package-plane.py \
  --repo-root . \
  --receipt /tmp/HUB_NO_SIBLINGS_PACKAGE_PLANE.generated.json
```

Local cross-repository development is an explicit compatibility mode only:

```bash
dotnet build Chummer.Run.Api/Chummer.Run.Api.csproj \
  -p:ChummerUseLocalCompatibilityTree=true
```

Neither compatibility mode nor its outputs are release evidence. Release and
CI receipts must use the locked package plane and an isolated NuGet cache.
