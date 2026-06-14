FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
ARG CHUMMER_BUILD_CONCURRENCY=1
WORKDIR /src
COPY chummercomplete/chummer.run-services/Chummer.Run.Identity/Chummer.Run.Identity.csproj chummercomplete/chummer.run-services/Chummer.Run.Identity/
COPY chummercomplete/chummer.run-services/Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Control.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Run.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Play.Contracts/
COPY chummercomplete/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummercomplete/chummer-core-engine/Chummer.Contracts/
COPY chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
RUN dotnet restore chummercomplete/chummer.run-services/Chummer.Run.Identity/Chummer.Run.Identity.csproj
COPY chummercomplete/chummer.run-services/Chummer.Run.Identity/ chummercomplete/chummer.run-services/Chummer.Run.Identity/
COPY chummercomplete/chummer.run-services/Chummer.Control.Contracts/ chummercomplete/chummer.run-services/Chummer.Control.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/ chummercomplete/chummer.run-services/Chummer.Run.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Play.Contracts/ chummercomplete/chummer.run-services/Chummer.Play.Contracts/
COPY chummercomplete/chummer-core-engine/Chummer.Contracts/ chummercomplete/chummer-core-engine/Chummer.Contracts/
COPY chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/ chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/ fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
WORKDIR /src/chummercomplete/chummer.run-services/Chummer.Run.Identity
RUN nice -n 10 dotnet build /src/chummercomplete/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummercomplete/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false \
 && nice -n 10 dotnet build /src/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false
RUN nice -n 10 dotnet publish -c Release -o /app/publish --nologo -m:${CHUMMER_BUILD_CONCURRENCY} -p:BuildInParallel=false -p:UseSharedCompilation=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Identity.dll"]
