using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Contracts.BuildGhost;
using Chummer.Contracts.Owners;
using Chummer.Infrastructure.Workspaces;

namespace Chummer.Run.Api.Services.InstallLinking;

/// <summary>
/// Host-only composition for one owner's explicitly consented, selected rule read.
/// No public route, provider, group visibility, caller-issued owner stamp or user-store
/// mutation is admitted here. The factory and its source/scratch roots are host-owned.
/// Returned Core observations are not continuing authorization or provider payloads.
/// </summary>
internal sealed class RookWorkspaceRuleReadService(
    RookWorkspaceReadAdmissionService admission,
    PrivateWorkspaceRuleRuntimeFactory runtimes)
{
    internal async Task<WorkspaceRuleQuestionResult> ResolveAsync(
        HttpRequest request,
        string installationId,
        string grantId,
        string consentId,
        long expectedConsentVersion,
        string intent,
        string savedSubjectId,
        string locale,
        CancellationToken ct = default)
    {
        ct.ThrowIfCancellationRequested();
        RookWorkspaceReadCapture captured = await admission.CaptureAsync(request,
            installationId, grantId, consentId, expectedConsentVersion, ct).ConfigureAwait(false);

        // Capture has left every account/install/PostgreSQL/snapshot gate before
        // any Core work. Cancellation cannot preempt Core's synchronous parsing,
        // file I/O or locks; it is checked around that work, not a hard deadline.
        WorkspaceRuleQuestionResult result = ResolveCaptured(captured, intent, savedSubjectId, locale, ct);

        // ResolveCaptured has already closed the private issuer, cleaned its scratch
        // and cleared our byte buffer. Do not place cleanup, provider work or another
        // await between this final fresh authorization check and releasing the result.
        await admission.RevalidateAsync(request, captured, ct).ConfigureAwait(false);
        ct.ThrowIfCancellationRequested();
        return result;
    }

    private WorkspaceRuleQuestionResult ResolveCaptured(RookWorkspaceReadCapture captured,
        string intent, string savedSubjectId, string locale, CancellationToken ct)
    {
        byte[] carrier = new byte[InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes];
        try
        {
            if (captured.Snapshot.WorkspaceContinuation is not JsonElement continuation
                || continuation.ValueKind != JsonValueKind.Object)
                throw Unavailable();

            // A fixed-capacity stream bounds the complete wire envelope without
            // converting private character JSON into another immutable string.
            using var stream = new MemoryStream(carrier, 0, carrier.Length, writable: true, publiclyVisible: false);
            stream.SetLength(0);
            using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions { MaxDepth = 128 }))
            {
                continuation.WriteTo(writer);
            }
            ct.ThrowIfCancellationRequested();
            OwnerScope owner = new(InstallLinkedWorkspaceSnapshotTransfer.ComputeContinuationOwnerId(
                captured.Account.SubjectId));
            // Only the persisted, freshly admitted explicit Rook consent permits
            // confirming this request-private restore. It never confirms a user write.
            using PrivateWorkspaceRuleRuntime runtime = runtimes.Create(owner,
                carrier.AsMemory(0, checked((int)stream.Length)), explicitlyConfirmed: true, cancellationToken: ct);
            if (!string.Equals(runtime.WorkspaceId.Value, captured.Consent.WorkspaceId, StringComparison.Ordinal)
                || !string.Equals(runtime.WorkspaceId.Value, captured.Snapshot.WorkspaceId, StringComparison.Ordinal))
                throw Unavailable();
            var question = new WorkspaceRuleQuestionRequest(runtime.WorkspaceId, runtime.ContentRevision,
                captured.Snapshot.RulesetId, intent, savedSubjectId, locale);
            return runtime.Resolve(runtime.OwnerStamp, question, ct);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw new OperationCanceledException("The Rook workspace read was canceled.", ct);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException
            or InvalidOperationException or ArgumentException or NotSupportedException or JsonException)
        {
            // Includes failed private cleanup: no result escapes and no carrier,
            // filesystem path, underlying exception or owner detail is disclosed.
            throw Unavailable();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(carrier);
        }
    }

    private static InstallLinkingOperationException Unavailable()
        => new(StatusCodes.Status503ServiceUnavailable, "The selected Rook rule read is unavailable.");
}
