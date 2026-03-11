#!/usr/bin/env bash
set -euo pipefail

dotnet test Chummer.Tests/Chummer.Tests.csproj \
  -c Release \
  -f net10.0 \
  -p:TargetFramework=net10.0 \
  --filter "FullyQualifiedName~BlazorShellComponentTests"
