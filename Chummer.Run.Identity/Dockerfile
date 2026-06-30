# syntax=docker/dockerfile:1.4
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG CHUMMER_BUILD_CONCURRENCY=1
WORKDIR /src
COPY --from=run-services-source Chummer.Run.Identity/Chummer.Run.Identity.csproj chummer.run-services/Chummer.Run.Identity/
COPY --from=run-services-source Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummer.run-services/Chummer.Control.Contracts/
COPY --from=run-services-source Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummer.run-services/Chummer.Run.Contracts/
COPY --from=run-services-source Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummer.run-services/Chummer.Play.Contracts/
COPY chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY --from=fleet-media-factory-contracts Chummer.Media.Contracts.csproj fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
RUN dotnet restore chummer.run-services/Chummer.Run.Identity/Chummer.Run.Identity.csproj
COPY --from=run-services-source Chummer.Run.Identity/ chummer.run-services/Chummer.Run.Identity/
COPY --from=run-services-source Chummer.Control.Contracts/ chummer.run-services/Chummer.Control.Contracts/
COPY --from=run-services-source Chummer.Run.Contracts/ chummer.run-services/Chummer.Run.Contracts/
COPY --from=run-services-source Chummer.Play.Contracts/ chummer.run-services/Chummer.Play.Contracts/
COPY chummer-core-engine/Chummer.Contracts/ chummer-core-engine/Chummer.Contracts/
COPY chummer-hub-registry/Chummer.Hub.Registry.Contracts/ chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY --from=fleet-media-factory-contracts . fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
WORKDIR /src/chummer.run-services/Chummer.Run.Identity
RUN nice -n 10 dotnet build /src/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false
RUN nice -n 10 dotnet publish -c Release -o /app/publish --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false -p:UseSharedCompilation=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Identity.dll"]
