FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY chummercomplete/chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj chummercomplete/chummer.run-services/Chummer.Run.Api/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Run.Contracts/
RUN dotnet restore chummercomplete/chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj
COPY chummercomplete/chummer.run-services/Chummer.Run.Api/ chummercomplete/chummer.run-services/Chummer.Run.Api/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/ chummercomplete/chummer.run-services/Chummer.Run.Contracts/
COPY chummercomplete/chummer.run-services/.codex-design/ chummercomplete/chummer.run-services/.codex-design/
COPY chummercomplete/chummer.run-services/Chummer.Play.Contracts/bin/Release/net10.0/ chummercomplete/chummer.run-services/Chummer.Play.Contracts/bin/Release/net10.0/
COPY chummercomplete/chummer-core-engine/Chummer.Contracts/bin/Release/net10.0/ chummercomplete/chummer-core-engine/Chummer.Contracts/bin/Release/net10.0/
COPY fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Release/net10.0/ fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Release/net10.0/
WORKDIR /src/chummercomplete/chummer.run-services/Chummer.Run.Api
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
COPY --from=build /src/chummercomplete/chummer.run-services/.codex-design /app/.codex-design
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Api.dll"]
