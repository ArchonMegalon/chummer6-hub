# syntax=docker/dockerfile:1.4
FROM python:3.12-slim@sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28 AS public-pwa-proof
WORKDIR /proof
COPY --from=run-services-source scripts/validate_public_pwa_proof_authority.py scripts/validate_public_pwa_proof_authority.py
COPY --from=run-services-source scripts/verify_public_pwa_static_assets.py scripts/verify_public_pwa_static_assets.py
COPY --from=run-services-source scripts/generate_public_play_worker_projection.py scripts/generate_public_play_worker_projection.py
COPY --from=run-services-source Chummer.Run.Api/public-pwa-proof-authority.json Chummer.Run.Api/public-pwa-proof-authority.json
COPY --from=run-services-source Chummer.Run.Api/play-pwa-required-inventory.json Chummer.Run.Api/play-pwa-required-inventory.json
COPY --from=run-services-source Chummer.Run.Api/play-pwa-mirrors.json Chummer.Run.Api/play-pwa-mirrors.json
COPY --from=run-services-source Chummer.Run.Api/play-worker-projection.json Chummer.Run.Api/play-worker-projection.json
COPY --from=run-services-source Chummer.Run.Api/service-worker.public-edge.template.js Chummer.Run.Api/service-worker.public-edge.template.js
COPY --from=run-services-source Chummer.Run.Api/wwwroot/mobile-install-shell.js Chummer.Run.Api/wwwroot/mobile-install-shell.js
COPY --from=run-services-source Chummer.Run.Api/wwwroot/mobile.css Chummer.Run.Api/wwwroot/mobile.css
COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.play.webmanifest Chummer.Run.Api/wwwroot/manifest.play.webmanifest
COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.player.webmanifest Chummer.Run.Api/wwwroot/manifest.player.webmanifest
COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.gm.webmanifest Chummer.Run.Api/wwwroot/manifest.gm.webmanifest
COPY --from=run-services-source Chummer.Run.Api/wwwroot/manifest.observer.webmanifest Chummer.Run.Api/wwwroot/manifest.observer.webmanifest
COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-192.png Chummer.Run.Api/wwwroot/icons/icon-192.png
COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-512.png Chummer.Run.Api/wwwroot/icons/icon-512.png
COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-192.svg Chummer.Run.Api/wwwroot/icons/icon-192.svg
COPY --from=run-services-source Chummer.Run.Api/wwwroot/icons/icon-512.svg Chummer.Run.Api/wwwroot/icons/icon-512.svg
COPY --from=run-services-source Chummer.Run.Api/wwwroot/mobile/service-worker.js Chummer.Run.Api/wwwroot/mobile/service-worker.js
COPY --from=run-services-source Chummer.Run.Api/wwwroot/service-worker.js Chummer.Run.Api/wwwroot/service-worker.js
RUN ["/usr/local/bin/python3", "-I", "-S", "scripts/validate_public_pwa_proof_authority.py", "--authority", "Chummer.Run.Api/public-pwa-proof-authority.json", "--verifier", "scripts/verify_public_pwa_static_assets.py", "--generator", "scripts/generate_public_play_worker_projection.py", "--inventory", "Chummer.Run.Api/play-pwa-required-inventory.json", "--mirror", "Chummer.Run.Api/play-pwa-mirrors.json", "--projection", "Chummer.Run.Api/play-worker-projection.json", "--template", "Chummer.Run.Api/service-worker.public-edge.template.js", "--receipt", "/proof/public-pwa-proof-authority.receipt.json"]

FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
COPY --from=public-pwa-proof /proof/public-pwa-proof-authority.receipt.json /tmp/public-pwa-proof-authority.receipt.json
ARG CHUMMER_BUILD_CONCURRENCY=1
WORKDIR /src
COPY --from=run-services-source Directory.Build.props chummer.run-services/
COPY --from=run-services-source Chummer.Run.Api/Chummer.Run.Api.csproj chummer.run-services/Chummer.Run.Api/
COPY --from=run-services-source Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj chummer.run-services/Chummer.InstallLinking.Postgres.Tool/
COPY --from=run-services-source Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj chummer.run-services/Chummer.Campaign.Contracts/
COPY --from=run-services-source Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummer.run-services/Chummer.Control.Contracts/
COPY --from=run-services-source Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummer.run-services/Chummer.Run.Contracts/
COPY --from=run-services-source Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummer.run-services/Chummer.Play.Contracts/
COPY --from=run-services-source Chummer.World.Contracts/Chummer.World.Contracts.csproj chummer.run-services/Chummer.World.Contracts/
COPY chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj chummer-hub-registry/Chummer.Run.Registry/
COPY --from=fleet-media-factory-contracts Chummer.Media.Contracts.csproj fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
RUN dotnet restore chummer.run-services/Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj
COPY --from=run-services-source Chummer.Run.Api/ chummer.run-services/Chummer.Run.Api/
COPY --from=run-services-source Chummer.InstallLinking.Postgres.Tool/ chummer.run-services/Chummer.InstallLinking.Postgres.Tool/
COPY --from=run-services-source Chummer.Campaign.Contracts/ chummer.run-services/Chummer.Campaign.Contracts/
COPY --from=run-services-source Chummer.Control.Contracts/ chummer.run-services/Chummer.Control.Contracts/
COPY --from=run-services-source Chummer.Run.Contracts/ chummer.run-services/Chummer.Run.Contracts/
COPY --from=run-services-source .codex-design/ chummer.run-services/.codex-design/
COPY --from=run-services-source Chummer.Play.Contracts/ chummer.run-services/Chummer.Play.Contracts/
COPY --from=run-services-source Chummer.World.Contracts/ chummer.run-services/Chummer.World.Contracts/
COPY chummer-core-engine/Chummer.Contracts/ chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/ chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummer-hub-registry/Chummer.Run.Registry/ chummer-hub-registry/Chummer.Run.Registry/
COPY chummer-hub-registry/black-ledger/ chummer-hub-registry/black-ledger/
COPY --from=fleet-media-factory-contracts . fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
WORKDIR /src/chummer.run-services/Chummer.Run.Api
RUN rm -rf /src/chummer.run-services/Chummer.Run.Api/bin /src/chummer.run-services/Chummer.Run.Api/obj
RUN nice -n 10 dotnet build /src/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer.run-services/Chummer.World.Contracts/Chummer.World.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false
RUN nice -n 10 dotnet publish -c Release -o /app/publish --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false -p:UseSharedCompilation=false
RUN nice -n 10 dotnet publish /src/chummer.run-services/Chummer.InstallLinking.Postgres.Tool/Chummer.InstallLinking.Postgres.Tool.csproj -c Release -o /app/install-linking-postgres-tool --no-restore --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false -p:UseSharedCompilation=false
RUN test -f /app/publish/wwwroot/service-worker.js \
 && grep -Fq 'const CACHE_VERSION = "v19";' /app/publish/wwwroot/service-worker.js \
 && grep -Fq 'const CACHE_CONTRACT = "run-api-projection-v2";' /app/publish/wwwroot/service-worker.js \
 && grep -Fq 'const CRITICAL_SHELL_ASSETS = [' /app/publish/wwwroot/service-worker.js \
 && grep -Fq '"/manifest.play.webmanifest"' /app/publish/wwwroot/service-worker.js \
 && grep -Fq 'play_public_route_network_unavailable' /app/publish/wwwroot/service-worker.js \
 && grep -Fq 'url.pathname.startsWith("/api/play/")' /app/publish/wwwroot/service-worker.js \
 && ! grep -Fq 'self.skipWaiting()' /app/publish/wwwroot/service-worker.js \
 && ! grep -Fq 'self.clients.claim()' /app/publish/wwwroot/service-worker.js \
 && ! grep -Fq '"/mobile-turn-companion.js"' /app/publish/wwwroot/service-worker.js

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS install-linking-postgres-tool-final
ARG CHUMMER_RUNTIME_UID=1654
ARG CHUMMER_RUNTIME_GID=1654
WORKDIR /app
COPY --from=build /app/install-linking-postgres-tool .
RUN set -eu; link="$(find -P /app -xdev -type l -print -quit)"; test -z "$link"; find -P /app -xdev -type d -exec chmod 0755 {} +; find -P /app -xdev -type f -exec chmod 0644 {} +
USER ${CHUMMER_RUNTIME_UID}:${CHUMMER_RUNTIME_GID}
ENTRYPOINT ["/bin/sh", "-c", "umask 077 && exec dotnet Chummer.InstallLinking.Postgres.Tool.dll \"$@\"", "install-linking-postgres-tool"]

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
ARG CHUMMER_RUNTIME_UID=1654
ARG CHUMMER_RUNTIME_GID=1654
WORKDIR /app
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && command -v setpriv >/dev/null
COPY --from=run-services-source --chmod=0555 scripts/initialize-public-edge-volumes.sh /usr/local/libexec/chummer/initialize-public-edge-volumes.sh
COPY --from=build /app/publish .
COPY --from=build /src/chummer.run-services/.codex-design /app/.codex-design
COPY --from=build /src/chummer-hub-registry/black-ledger /app/black-ledger
COPY --from=design-product products/chummer/ /app/.codex-design/product/
RUN set -eu; link="$(find -P /app -xdev -type l -print -quit)"; test -z "$link"; find -P /app -xdev -type d -exec chmod 0755 {} +; find -P /app -xdev -type f -exec chmod 0644 {} +; mkdir -p /app/state; chown -R "${CHUMMER_RUNTIME_UID}:${CHUMMER_RUNTIME_GID}" /app/state; chmod -R go-rwx /app/state
ENV ASPNETCORE_URLS=http://+:8080
USER ${CHUMMER_RUNTIME_UID}:${CHUMMER_RUNTIME_GID}
ENTRYPOINT ["/bin/sh", "-c", "umask 077 && exec dotnet Chummer.Run.Api.dll"]
