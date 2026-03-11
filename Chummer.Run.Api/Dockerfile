FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj chummer.run-services/Chummer.Run.Api/
COPY chummer-core-engine/Chummer/Chummer.csproj chummer-core-engine/Chummer/
COPY chummer-core-engine/Chummer.Contracts/Chummer.Contracts.csproj chummer-core-engine/Chummer.Contracts/
RUN dotnet restore chummer.run-services/Chummer.Run.Api/Chummer.Run.Api.csproj
COPY chummer.run-services/Chummer.Run.Api/ chummer.run-services/Chummer.Run.Api/
COPY chummer-core-engine/Chummer/ chummer-core-engine/Chummer/
COPY chummer-core-engine/Chummer.Contracts/ chummer-core-engine/Chummer.Contracts/
WORKDIR /src/chummer.run-services/Chummer.Run.Api
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS final
WORKDIR /app
COPY --from=build /app/publish .
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Chummer.Run.Api.dll"]
