namespace Chummer.Run.Api.Services.Community;

public sealed class RunsiteTourQuotaService
{
    private readonly HorizonArtifactQuotaService _quota;
    private readonly HorizonCapabilityService _capabilities;

    public RunsiteTourQuotaService(
        HorizonArtifactQuotaService quota,
        HorizonCapabilityService capabilities)
    {
        _quota = quota;
        _capabilities = capabilities;
    }

    public RunsiteTourQuotaSnapshot GetQuota(
        string userId,
        DateTimeOffset? now = null,
        string? email = null)
        => ToRunsiteSnapshot(_quota.GetQuota(new HorizonArtifactQuotaRequest(userId, "runsite", "tour", email), now));

    public RunsiteTourQuotaSnapshot ConsumeTour(string userId, DateTimeOffset? now = null, string? email = null)
    {
        try
        {
            return ToRunsiteSnapshot(_quota.Consume(new HorizonArtifactQuotaRequest(userId, "runsite", "tour", email), now));
        }
        catch (InvalidOperationException ex) when (ex.Message.Contains("allowance is exhausted", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("3D-tour allowance is exhausted for this week.", ex);
        }
    }

    public HorizonCapabilityHealthSnapshot GetCapabilityHealth(bool publicSafe = false)
        => _capabilities.GetHealth("runsite", "tour", publicSafe);

    private static RunsiteTourQuotaSnapshot ToRunsiteSnapshot(HorizonArtifactQuotaSnapshot snapshot)
        => new(
            snapshot.UserId,
            snapshot.SupporterActive,
            snapshot.AllowanceTier,
            snapshot.EntitlementBasis,
            snapshot.EntitlementScope,
            snapshot.WeeklyLimit,
            snapshot.WeeklyUsed,
            snapshot.WeeklyRemaining,
            snapshot.WindowStartUtc,
            snapshot.WindowEndUtc);
}

public sealed record RunsiteTourQuotaSnapshot(
    string UserId,
    bool SupporterActive,
    string AllowanceTier,
    string EntitlementBasis,
    string EntitlementScope,
    int WeeklyLimit,
    int WeeklyUsed,
    int WeeklyRemaining,
    DateTimeOffset WindowStartUtc,
    DateTimeOffset WindowEndUtc);
