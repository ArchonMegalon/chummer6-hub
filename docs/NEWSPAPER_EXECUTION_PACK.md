# Newspaper Execution Pack

This repository now contains a clean-room scaffold for a structured personal newspaper pipeline.

## Implemented paths

- Contracts: `Chummer.Run.Contracts/NewspaperContracts.cs`
- API endpoints: `Chummer.Run.AI/Controllers/NewspaperController.cs`
- Composition service: `Chummer.Run.AI/Services/Newspaper/NewspaperCompositionService.cs`
- Validation guardrails: `Chummer.Run.AI/Services/Newspaper/NewspaperValidationService.cs`
- HTML renderer: `Chummer.Run.AI/Services/Newspaper/NewspaperHtmlRenderer.cs`
- Provider adapters:
  - `BrowserActClient`
  - `PeekShotClient`
  - `MarkupGoClient`
  in `Chummer.Run.AI/Services/Newspaper/ProviderAdapters.cs`
- Templates:
  - `Chummer.Run.AI/Templates/Newspaper/issue.html`
  - `Chummer.Run.AI/Templates/Newspaper/styles/base.css`
  - `Chummer.Run.AI/Templates/Newspaper/styles/components.css`
  - `Chummer.Run.AI/Templates/Newspaper/styles/print.css`
- Schemas:
  - `Chummer.Run.AI/Schemas/Newspaper/issue.schema.json`
  - `Chummer.Run.AI/Schemas/Newspaper/story.schema.json`

## API surface

- `POST /api/v1/ai/newspaper/issue/compose`
  - Input: `ComposeIssueRequest`
  - Output: `ComposeIssueResponse` (issue + validation report)
- `POST /api/v1/ai/newspaper/issue/render-html`
  - Input: `RenderIssueHtmlRequest`
  - Output: `RenderIssueHtmlResponse`
- `POST /api/v1/ai/newspaper/issue/render-pdf`
  - Input: `RenderIssueHtmlRequest`
  - Output: `application/pdf` via MarkupGo adapter

## Quality gates implemented

- Minimum estimated page count
- Minimum image count
- Visual required for each feature story
- Summary max-length checks
- Diagnostic/debug token rejection
- Cover long-summary overflow check

## Smoke command

Run:

```bash
bash scripts/ai/newspaper_smoke.sh
```

## Next milestones

1. Replace placeholder adapter endpoints with real provider auth and request/response contracts.
2. Add webhooks/polling orchestration for BrowserAct jobs.
3. Add explicit fallback mode routing and Telegram delivery wiring.
4. Add real PDF quality tests (page count + image presence) on generated artifacts.
