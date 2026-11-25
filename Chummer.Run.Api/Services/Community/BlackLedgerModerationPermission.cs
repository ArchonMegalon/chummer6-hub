namespace Chummer.Run.Api.Services.Community;

// A request-scoped permission minted only from fresh server-side Identity truth.
// Neither a HubUserDto, request role/flag nor faction membership grants moderation.
public sealed class BlackLedgerModerationPermission
{
    private readonly DateTimeOffset _expiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(1);

    private BlackLedgerModerationPermission(AuthenticatedHubSubject subject) => Subject = subject;

    internal AuthenticatedHubSubject Subject { get; }

    public static async Task<BlackLedgerModerationPermission> RequireAsync(
        HubIdentityClient identity, HttpRequest request, CancellationToken cancellationToken)
    {
        var subject = await identity.RequireFreshSubjectAsync(request, cancellationToken);
        // Identity assigns these roles. A release-upload email grant is scoped to uploads.
        if (subject.Roles?.Any(role =>
                string.Equals(role?.Trim(), "operator", StringComparison.OrdinalIgnoreCase)
                || string.Equals(role?.Trim(), "admin", StringComparison.OrdinalIgnoreCase)) != true)
        {
            throw Denied();
        }

        return new BlackLedgerModerationPermission(subject);
    }

    internal string RequireSubjectId()
    {
        if (DateTimeOffset.UtcNow >= _expiresAtUtc || string.IsNullOrWhiteSpace(Subject.SubjectId))
        {
            throw Denied();
        }

        return Subject.SubjectId;
    }

    internal static HubRequestAuthException Denied()
        => new(StatusCodes.Status403Forbidden, "Faction moderation permission is required.");
}
