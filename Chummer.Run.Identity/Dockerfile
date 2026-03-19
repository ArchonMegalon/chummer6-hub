FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY chummercomplete/chummer.run-services/Chummer.Run.Identity/Chummer.Run.Identity.csproj chummercomplete/chummer.run-services/Chummer.Run.Identity/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/Chummer.Run.Contracts.csproj chummercomplete/chummer.run-services/Chummer.Run.Contracts/
RUN dotnet restore chummercomplete/chummer.run-services/Chummer.Run.Identity/Chummer.Run.Identity.csproj
COPY chummercomplete/chummer.run-services/Chummer.Run.Identity/ chummercomplete/chummer.run-services/Chummer.Run.Identity/
COPY chummercomplete/chummer.run-services/Chummer.Run.Contracts/ chummercomplete/chummer.run-services/Chummer.Run.Contracts/
COPY chummercomplete/chummer.run-services/Chummer.Play.Contracts/bin/Release/net10.0/ chummercomplete/chummer.run-services/Chummer.Play.Contracts/bin/Release/net10.0/
COPY chummercomplete/chummer-core-engine/Chummer.Contracts/bin/Release/net10.0/ chummercomplete/chummer-core-engine/Chummer.Contracts/bin/Release/net10.0/
COPY fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Release/net10.0/ fleet/repos/chummer-media-factory/src/Chummer.Media.Contracts/bin/Release/net10.0/
WORKDIR /src/chummercomplete/chummer.run-services/Chummer.Run.Identity
RUN dotnet publish -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Identity.dll"]
