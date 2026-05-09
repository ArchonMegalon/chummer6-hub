FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY chummercomplete/chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj chummercomplete/chummer.run-services/Chummer.Run.Api/
COPY chummercomplete/chummer.run-services/Chummer.Campaign.Contracts/Chummer.Campaign.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Campaign.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Control.Contracts/Chummer.Control.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Control.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Run.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Play.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.World.Contracts/Chummer.World.Contracts.csproj chummercomplete/chummer.run-services/Chummer.World.Contracts/
COPY chummercomplete/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummercomplete/chummer-core-engine/Chummer.Contracts/
COPY chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummercomplete/chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj chummercomplete/chummer-hub-registry/Chummer.Run.Registry/
COPY fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
RUN dotnet restore chummercomplete/chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj
COPY chummercomplete/chummer.run-services/Chummer.Run.Api/ chummercomplete/chummer.run-services/Chummer.Run.Api/
COPY chummercomplete/chummer.run-services/Chummer.Campaign.Contracts/ chummercomplete/chummer.run-services/Chummer.Campaign.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Control.Contracts/ chummercomplete/chummer.run-services/Chummer.Control.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/ chummercomplete/chummer.run-services/Chummer.Run.Contracts/
COPY chummercomplete/chummer.run-services/.codex-design/ chummercomplete/chummer.run-services/.codex-design/
COPY chummercomplete/chummer.run-services/Chummer.Play.Contracts/ chummercomplete/chummer.run-services/Chummer.Play.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.World.Contracts/ chummercomplete/chummer.run-services/Chummer.World.Contracts/
COPY chummercomplete/chummer-core-engine/Chummer.Contracts/ chummercomplete/chummer-core-engine/Chummer.Contracts/
COPY chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/ chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/
COPY chummercomplete/chummer-hub-registry/Chummer.Run.Registry/ chummercomplete/chummer-hub-registry/Chummer.Run.Registry/
COPY fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/ fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/
WORKDIR /src/chummercomplete/chummer.run-services/Chummer.Run.Api
RUN dotnet build /src/chummercomplete/chummer.run-services/Chummer.Play.Contracts/Chummer.Play.Contracts.csproj -c Release --nologo \
 && dotnet build /src/chummercomplete/chummer.run-services/Chummer.World.Contracts/Chummer.World.Contracts.csproj -c Release --nologo \
 && dotnet build /src/chummercomplete/chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj -c Release --nologo \
 && dotnet build /src/chummercomplete/chummer-hub-registry/Chummer.Hub.Registry.Contracts/Chummer.Hub.Registry.Contracts.csproj -c Release --nologo \
 && dotnet build /src/chummercomplete/chummer-hub-registry/Chummer.Run.Registry/Chummer.Run.Registry.csproj -c Release --nologo \
 && dotnet build /src/fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/Chummer.Media.Contracts.csproj -c Release --nologo
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
COPY --from=build /src/chummercomplete/chummer.run-services/.codex-design /app/.codex-design
COPY chummercomplete/chummer-design/products/chummer/ /app/.codex-design/product/
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Api.dll"]
