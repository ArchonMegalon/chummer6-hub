# Hosted Feedback And Operator Consumers

Purpose: keep feedback loops and operator boards bounded as advisory, receipt-bearing consumers of canonical state.

## Advisory feedback inputs

- artifact and publisher/player feedback enters through registry-owned review surfaces: `HubRegistryController.AddReview`, `PublicationsController.Review`, `PublicationsController.Moderate`
- hosted approval-aware delivery feedback enters through `SpiderController.QueueManual`, `SpiderController.ExecuteAction`, and `DeliveryOutboxService.RecordAction`
- GM prep and reveal feedback enters through `GmOpsBoardController.UpdateChecklist`, `GmOpsBoardController.Reveal`, and `GmOpsBoardService.GetProjection`

## Operator consumer surfaces

- session/operator board projection: `GmOpsBoardController.GetProjection`
- hosted pipeline projection: `PipelineObservabilityController.GetProjection`
- registry/operator read models stay in the owner repo: `HubRegistryController.ListProjections`, `HubRegistryController.GetPipelineProjection`, `PublicationsController.List`

## Consumer rule

- feedback is advisory input with receipts; it must not overwrite canonical session, registry, or publication truth directly
- operator boards must compose ledger, delivery, registry, and pipeline projections without becoming hidden write-owning side systems
- approval state, checklist state, and outbox actions may append bounded operational history, but canonical publication/install/review truth still belongs to registry-owned surfaces
- hosted operator views must stay downstream of canonical read models and runtime receipts

## Verification path

- `tests/RunServicesVerification/GmOpsBoardVerification.cs` proves ops-board projection and approval-aware reveal behavior
- `tests/RunServicesVerification/PublicationVerification.cs` proves publication review/moderation receipts
- `tests/RunServicesVerification/PipelineProjectionVerification.cs` proves operator pipeline projections
- `tests/RunServicesVerification/HubExtractionReadinessVerification.cs` asserts the consumer-rule seams and sibling registry ownership references

## Current gap

- richer player/GM/publisher feedback UX is still product work
- the bounded consumer rule is now explicit, but deeper downstream workflow depth is still open
