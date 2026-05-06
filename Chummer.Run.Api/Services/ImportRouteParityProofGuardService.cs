namespace Chummer.Run.Api.Services;

public sealed class ImportRouteParityProofGuardService
{
    public static readonly string[] RequiredDirectProofReceiptIds =
    [
        "menu:translator",
        "menu:xml_editor",
        "menu:hero_lab_importer",
        "workflow:import_oracle"
    ];

    private readonly LocalReleaseProofArtifactService _localReleaseProof;

    public ImportRouteParityProofGuardService(IConfiguration configuration)
    {
        _localReleaseProof = new LocalReleaseProofArtifactService(configuration);
    }

    public ImportRouteParityProofGuardSnapshot Evaluate()
    {
        LocalReleaseProofSnapshot? snapshot = _localReleaseProof.LoadSnapshot();
        if (snapshot is null)
        {
            return new ImportRouteParityProofGuardSnapshot(
                false,
                "the current local release-proof package is unavailable, so direct proof receipts for translator, XML amendment, Hero Lab, and adjacent import routes are not current");
        }

        if (!snapshot.IsCurrent)
        {
            string reason = string.IsNullOrWhiteSpace(snapshot.CurrentnessReason)
                ? "the current local release-proof package is not current, so direct proof receipts for translator, XML amendment, Hero Lab, and adjacent import routes are not current"
                : snapshot.CurrentnessReason!.Trim().TrimEnd('.');
            return new ImportRouteParityProofGuardSnapshot(false, reason);
        }

        string[] publishedReceiptIds = snapshot.Receipts
            .Select(static receipt => receipt.ReceiptId)
            .Where(static receiptId => !string.IsNullOrWhiteSpace(receiptId))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        string[] missingReceiptIds = RequiredDirectProofReceiptIds
            .Where(requiredId => !publishedReceiptIds.Contains(requiredId, StringComparer.OrdinalIgnoreCase))
            .ToArray();
        if (missingReceiptIds.Length > 0)
        {
            return new ImportRouteParityProofGuardSnapshot(
                false,
                $"the current local release-proof package does not publish direct proof receipts for translator, XML amendment, Hero Lab, and adjacent import routes: {string.Join(", ", missingReceiptIds)}");
        }

        return new ImportRouteParityProofGuardSnapshot(true, null);
    }
}

public sealed record ImportRouteParityProofGuardSnapshot(
    bool IsCurrent,
    string? ReviewRequiredReason);
