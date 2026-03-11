# Hub Extraction Acceptance

`docs/hosted-boundary.manifest`, `docs/HOSTED_BOUNDARY.md`, and `tests/RunServicesVerification/CompatibilityVerification.cs` keep the hosted boundary limited to the canonical `Chummer.Run.*`, `Chummer.Play.Contracts`, and `Chummer.Media.Contracts` surface, require the active hosted boundary to run through `Chummer.Run.Api`, target the hosted runtime on `net10.0`, and block retired legacy roots (`Chummer`, `Chummer.Api`, `ChummerDataViewer`, `ChummerHub`, `Plugins/ChummerHub.Client`, `Plugins/SamplePlugin`, `TextblockConverter`, and `Translator`) from re-entering the repo.

## Worklist and issue anchors

This acceptance gate closes the hosted split/purification work tracked under:

- WL-085
- WL-086
- WL-088
- WL-089
- WL-095
- WL-098
- WL-102
- WL-104
- WL-111
- WL-118
- WL-120
- WL-125
- WL-137
- WL-140
- WL-145
- WL-148
- WL-149
- WL-150
- WL-151
- WL-153
- WL-155

Issue and migration anchors preserved in this acceptance narrative:

- 1926
- 2369
- 3948
- 4333
- 4334
- 4338
- 4339
- 4367
- 8667
- 8668
- 8697
- 8698
- 11709
- 21817
- 21924
- 53652
- 53653
- 53654

## Boundary artifacts that must stay aligned

- Chummer.Run.Registry
- Chummer.Play.Contracts
- Chummer.Media.Contracts
- PublicationVerification.cs
- CompatibilityVerification.cs
- HOSTED_BOUNDARY.md
- hosted-boundary.manifest
- .codex-design/product/README.md
- .codex-design/repo/IMPLEMENTATION_SCOPE.md
- .codex-design/review/REVIEW_CONTEXT.md
- PROGRAM_MILESTONES.yaml
- scripts/ai/verify.sh
