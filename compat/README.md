`compat/Chummer.Media.Contracts.dll` is the CI fallback snapshot for `Chummer.Run.Contracts` when the owner repo is unavailable in GitHub Actions.

- Source repo: `ArchonMegalon/chummer6-media-factory`
- Source commit: `f6af2c7929beca22858fb50ba8a6e22b934e3ab6`
- SHA-256: `e01c151887add7805d75cdb5b93ece588e1ad74cd00aee19862125d670ece1c6`
- Refresh command: `dotnet build /docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo && cp /docker/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Release/net10.0/Chummer.Media.Contracts.dll compat/Chummer.Media.Contracts.dll`
