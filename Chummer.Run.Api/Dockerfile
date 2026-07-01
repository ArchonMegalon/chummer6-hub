# syntax=docker/dockerfile:1.4
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG CHUMMER_BUILD_CONCURRENCY=1
WORKDIR /src
COPY --from=run-services-source Chummer.Run.Api/Chummer.Run.Api.csproj chummer.run-services/Chummer.Run.Api/
COPY --from=run-services-source Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj chummer.run-services/Chummer.Campaign.Contracts/
COPY --from=run-services-source Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummer.run-services/Chummer.Control.Contracts/
COPY --from=run-services-source Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummer.run-services/Chummer.Run.Contracts/
COPY --from=run-services-source Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummer.run-services/Chummer.Play.Contracts/
COPY --from=run-services-source Chummer.World.Contracts/Chummer.World.Contracts.csproj chummer.run-services/Chummer.World.Contracts/
COPY chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj chummer-hub-registry/Chummer.Run.Registry/
COPY --from=fleet-media-factory-contracts Chummer.Media.Contracts.csproj fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
RUN dotnet restore chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj
COPY --from=run-services-source Chummer.Run.Api/ chummer.run-services/Chummer.Run.Api/
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
RUN nice -n 10 dotnet build /src/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer.run-services/Chummer.World.Contracts/Chummer.World.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false
RUN nice -n 10 dotnet publish -c Release -o /app/publish --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false -p:UseSharedCompilation=false
RUN test -f /app/publish/wwwroot/service-worker.js \
 && grep -q 'const CACHE_NAME = "chummer-public-v4";' /app/publish/wwwroot/service-worker.js \
 && ! grep -q 'play-shell-v' /app/publish/wwwroot/service-worker.js

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
COPY --from=build /src/chummer.run-services/.codex-design /app/.codex-design
COPY --from=build /src/chummer-hub-registry/black-ledger /app/black-ledger
COPY --from=design-product products/chummer/ /app/.codex-design/product/
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Api.dll"]
