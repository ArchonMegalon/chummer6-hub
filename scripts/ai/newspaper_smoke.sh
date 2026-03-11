#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/_env.sh"

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

required_files=(
  "Chummer.Run.AI/Controllers/NewspaperController.cs"
  "Chummer.Run.AI/Services/Newspaper/NewspaperCompositionService.cs"
  "Chummer.Run.AI/Services/Newspaper/NewspaperValidationService.cs"
  "Chummer.Run.AI/Services/Newspaper/NewspaperHtmlRenderer.cs"
  "Chummer.Run.AI/Templates/Newspaper/issue.html"
  "Chummer.Run.AI/Templates/Newspaper/styles/print.css"
  "Chummer.Run.AI/Schemas/Newspaper/issue.schema.json"
  "Chummer.Run.AI/Schemas/Newspaper/story.schema.json"
)

for file in "${required_files[@]}"; do
  if [ ! -f "$file" ]; then
    echo "missing required file: $file" >&2
    exit 1
  fi
done

dotnet build Chummer.Run.Contracts/Chummer.Run.Contracts.csproj --nologo
dotnet build Chummer.Run.AI/Chummer.Run.AI.csproj --nologo

echo "newspaper smoke passed"
