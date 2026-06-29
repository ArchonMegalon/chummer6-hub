# syntax=docker/dockerfile:1.4
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG CHUMMER_BUILD_CONCURRENCY=1
WORKDIR /src
COPY chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj chummer.run-services/Chummer.Run.Api/
COPY chummer.run-services/Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj chummer.run-services/Chummer.Campaign.Contracts/
COPY chummer.run-services/Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummer.run-services/Chummer.Control.Contracts/
COPY chummer.run-services/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummer.run-services/Chummer.Run.Contracts/
COPY chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummer.run-services/Chummer.Play.Contracts/
COPY chummer.run-services/Chummer.World.Contracts/Chummer.World.Contracts.csproj chummer.run-services/Chummer.World.Contracts/
COPY chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj chummer-hub-registry/Chummer.Run.Registry/
COPY --from=fleet-media-factory src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
RUN dotnet restore chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj
COPY chummer.run-services/Chummer.Run.Api/ chummer.run-services/Chummer.Run.Api/
COPY chummer.run-services/Chummer.Campaign.Contracts/ chummer.run-services/Chummer.Campaign.Contracts/
COPY chummer.run-services/Chummer.Control.Contracts/ chummer.run-services/Chummer.Control.Contracts/
COPY chummer.run-services/Chummer.Run.Contracts/ chummer.run-services/Chummer.Run.Contracts/
COPY chummer.run-services/.codex-design/ chummer.run-services/.codex-design/
COPY chummer.run-services/Chummer.Play.Contracts/ chummer.run-services/Chummer.Play.Contracts/
COPY chummer.run-services/Chummer.World.Contracts/ chummer.run-services/Chummer.World.Contracts/
COPY chummer-core-engine/Chummer.Contracts/ chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/ chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummer-hub-registry/Chummer.Run.Registry/ chummer-hub-registry/Chummer.Run.Registry/
COPY chummer-hub-registry/black-ledger/ chummer-hub-registry/black-ledger/
COPY --from=fleet-media-factory src/Chummer.Media.Contracts/ fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
WORKDIR /src/chummer.run-services/Chummer.Run.Api
RUN nice -n 10 dotnet build /src/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer.run-services/Chummer.World.Contracts/Chummer.World.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false
RUN nice -n 10 dotnet publish -c Release -o /app/publish --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false -p:UseSharedCompilation=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
COPY --from=build /src/chummer.run-services/.codex-design /app/.codex-design
COPY --from=build /src/chummer-hub-registry/black-ledger /app/black-ledger
COPY chummer-design/products/chummer/ /app/.codex-design/product/
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Api.dll"]
