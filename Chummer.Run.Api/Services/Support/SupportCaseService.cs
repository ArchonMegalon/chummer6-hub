using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportCaseService
{
    private static readonly HashSet<string> AllowedKinds =
    [
        SupportCaseKinds.CrashReport,
        SupportCaseKinds.BugReport,
        SupportCaseKinds.Feedback,
        SupportCaseKinds.InstallHelp
    ];

    private static readonly HashSet<string> AllowedStatuses =
    [
        SupportCaseStatuses.New,
        SupportCaseStatuses.Clustered,
        SupportCaseStatuses.Routed,
        SupportCaseStatuses.AwaitingEvidence,
        SupportCaseStatuses.Accepted,
        SupportCaseStatuses.Fixed,
        SupportCaseStatuses.Deferred,
        SupportCaseStatuses.Rejected,
        SupportCaseStatuses.ReleasedToReporterChannel,
        SupportCaseStatuses.UserNotified
    ];

    private readonly SupportStore _store;
    private readonly ILogger<SupportCaseService> _logger;

    public SupportCaseService(SupportStore store, ILogger<SupportCaseService> logger)
    {
        _store = store;
        _logger = logger;
    }

    public SupportCaseProjection Submit(string? reporterUserId, string? reporterSubjectId, SupportCaseSubmitRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string kind = NormalizeKind(request.Kind);
        string title = NormalizeRequired(request.Title, nameof(request.Title), 160);
        string summary = NormalizeRequired(request.Summary, nameof(request.Summary), 280);
        string detail = NormalizeRequired(request.Detail, nameof(request.Detail), 8000);
        string? userId = NormalizeOptional(reporterUserId, 64);
        string? subjectId = NormalizeOptional(reporterSubjectId, 128);
        string? reporterEmail = NormalizeOptional(request.ReporterEmail, 256);
        string? installationId = NormalizeOptional(request.InstallationId, 64);
        string? applicationVersion = NormalizeOptional(request.ApplicationVersion, 64);
        string? releaseChannel = NormalizeOptional(request.ReleaseChannel, 64);
        string? headId = NormalizeOptional(request.HeadId, 64);
        string? platform = NormalizeOptional(request.Platform, 64);
        string? arch = NormalizeOptional(request.Arch, 32);
        string source = NormalizeSource(request.Source);
        bool designImpact = LooksLikeDesignImpact(title, summary, detail);
        string candidateOwnerRepo = ResolveCandidateOwnerRepo(kind, title, summary, detail, headId, platform, installationId, designImpact);
        string clusterKey = ComputeClusterKey(
            kind,
            title,
            summary,
            reporterEmail,
            userId,
            subjectId,
            installationId,
            applicationVersion,
            releaseChannel,
            headId,
            candidateOwnerRepo);
        DateTimeOffset now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            if (_store.CaseIdByClusterKey.TryGetValue(clusterKey, out string? existingCaseId)
                && _store.CasesById.TryGetValue(existingCaseId, out SupportCaseProjection? existing))
            {
                SupportCaseProjection updated = existing with
                {
                    Status = existing.Status == SupportCaseStatuses.New ? SupportCaseStatuses.Clustered : existing.Status,
                    UpdatedAtUtc = now,
                    ReporterEmail = reporterEmail ?? existing.ReporterEmail,
                    ApplicationVersion = applicationVersion ?? existing.ApplicationVersion,
                    ReleaseChannel = releaseChannel ?? existing.ReleaseChannel,
                    HeadId = headId ?? existing.HeadId,
                    Platform = platform ?? existing.Platform,
                    Arch = arch ?? existing.Arch,
                    InstallationId = installationId ?? existing.InstallationId,
                    Timeline = AppendTimeline(
                        existing.Timeline,
                        BuildEvent(
                            status: existing.Status == SupportCaseStatuses.New ? SupportCaseStatuses.Clustered : existing.Status,
                            summary: "A matching report was added to the existing support case.",
                            occurredAtUtc: now,
                            actor: source,
                            metadata: BuildMetadata(
                                ("source", source),
                                ("candidate_owner_repo", candidateOwnerRepo))))
                };
                _store.CasesById[updated.CaseId] = updated;
                _store.PersistLocked();
                return updated;
            }

            string caseId = $"support_case_{NewIdFragment()}";
            SupportCaseProjection created = new(
                CaseId: caseId,
                ClusterKey: clusterKey,
                Kind: kind,
                Status: SupportCaseStatuses.New,
                Title: title,
                Summary: summary,
                Detail: detail,
                CandidateOwnerRepo: candidateOwnerRepo,
                DesignImpactSuspected: designImpact,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                Source: source,
                ReporterEmail: reporterEmail,
                ReporterUserId: userId,
                ReporterSubjectId: subjectId,
                InstallationId: installationId,
                ApplicationVersion: applicationVersion,
                ReleaseChannel: releaseChannel,
                HeadId: headId,
                Platform: platform,
                Arch: arch,
                RelatedIds: Array.Empty<string>(),
                Timeline:
                [
                    BuildEvent(
                        status: SupportCaseStatuses.New,
                        summary: "Support case submitted.",
                        occurredAtUtc: now,
                        actor: source,
                        metadata: BuildMetadata(
                            ("candidate_owner_repo", candidateOwnerRepo),
                            ("design_impact_suspected", designImpact ? "true" : "false")))
                ]);

            _store.CasesById[caseId] = created;
            _store.CaseIdByClusterKey[clusterKey] = caseId;
            _store.PersistLocked();
            _logger.LogInformation("Accepted support case {CaseId} ({Kind}) for {CandidateOwnerRepo}.", caseId, kind, candidateOwnerRepo);
            return created;
        }
    }

    public SupportCaseProjection UpsertFromCrash(
        CrashIncidentProjection incident,
        CrashClusterProjection cluster,
        CrashWorkItemProjection workItem)
    {
        ArgumentNullException.ThrowIfNull(incident);
        ArgumentNullException.ThrowIfNull(cluster);
        ArgumentNullException.ThrowIfNull(workItem);

        DateTimeOffset now = DateTimeOffset.UtcNow;
        string clusterKey = $"crash:{workItem.WorkItemId}";
        string mappedStatus = MapCrashStatus(workItem.Status);
        bool designImpact = LooksLikeDesignImpact(
            incident.Envelope.ExceptionType,
            workItem.Summary,
            incident.Envelope.ExceptionMessage + "\n" + incident.Envelope.ExceptionDetail);

        lock (_store.Gate)
        {
            if (_store.CaseIdByClusterKey.TryGetValue(clusterKey, out string? existingCaseId)
                && _store.CasesById.TryGetValue(existingCaseId, out SupportCaseProjection? existing))
            {
                HashSet<string> relatedIds = new(existing.RelatedIds ?? Array.Empty<string>(), StringComparer.OrdinalIgnoreCase)
                {
                    incident.IncidentId,
                    workItem.WorkItemId
                };
                SupportCaseProjection updated = existing with
                {
                    Status = mappedStatus,
                    UpdatedAtUtc = now,
                    Summary = workItem.Summary,
                    Detail = BuildCrashDetail(incident, cluster, workItem),
                    CandidateOwnerRepo = workItem.CandidateOwnerRepo,
                    DesignImpactSuspected = existing.DesignImpactSuspected || designImpact,
                    ReporterEmail = existing.ReporterEmail,
                    ReporterUserId = NormalizeOptional(incident.Envelope.UserId, 64) ?? existing.ReporterUserId,
                    ReporterSubjectId = NormalizeOptional(incident.Envelope.SubjectId, 128) ?? existing.ReporterSubjectId,
                    InstallationId = NormalizeOptional(incident.Envelope.InstallationId, 64) ?? existing.InstallationId,
                    ApplicationVersion = incident.Envelope.ApplicationVersion,
                    ReleaseChannel = incident.RegistryContext.ReleaseChannel ?? existing.ReleaseChannel,
                    HeadId = incident.Envelope.DesktopHead ?? incident.Envelope.HeadId,
                    Platform = incident.RegistryContext.Platform ?? existing.Platform,
                    Arch = incident.Envelope.ProcessArchitecture,
                    RelatedIds = relatedIds.OrderBy(static item => item, StringComparer.OrdinalIgnoreCase).ToArray(),
                    Timeline = AppendTimeline(
                        existing.Timeline,
                        BuildEvent(
                            status: mappedStatus,
                            summary: $"Crash incident {incident.IncidentId} reached support triage.",
                            occurredAtUtc: now,
                            actor: SupportCaseSourceKinds.DesktopCrash,
                            metadata: BuildMetadata(
                                ("work_item_id", workItem.WorkItemId),
                                ("crash_fingerprint", cluster.CrashFingerprint),
                                ("occurrence_count", cluster.OccurrenceCount.ToString(System.Globalization.CultureInfo.InvariantCulture)))))
                };
                _store.CasesById[updated.CaseId] = updated;
                _store.CrashCaseIdByWorkItemId[workItem.WorkItemId] = updated.CaseId;
                _store.PersistLocked();
                return updated;
            }

            string caseId = $"support_case_{NewIdFragment()}";
            SupportCaseProjection created = new(
                CaseId: caseId,
                ClusterKey: clusterKey,
                Kind: SupportCaseKinds.CrashReport,
                Status: mappedStatus,
                Title: $"Crash: {incident.Envelope.ExceptionType}",
                Summary: workItem.Summary,
                Detail: BuildCrashDetail(incident, cluster, workItem),
                CandidateOwnerRepo: workItem.CandidateOwnerRepo,
                DesignImpactSuspected: designImpact,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                Source: SupportCaseSourceKinds.DesktopCrash,
                ReporterEmail: null,
                ReporterUserId: NormalizeOptional(incident.Envelope.UserId, 64),
                ReporterSubjectId: NormalizeOptional(incident.Envelope.SubjectId, 128),
                InstallationId: NormalizeOptional(incident.Envelope.InstallationId, 64),
                ApplicationVersion: incident.Envelope.ApplicationVersion,
                ReleaseChannel: incident.RegistryContext.ReleaseChannel,
                HeadId: incident.Envelope.DesktopHead ?? incident.Envelope.HeadId,
                Platform: incident.RegistryContext.Platform,
                Arch: incident.Envelope.ProcessArchitecture,
                RelatedIds: [incident.IncidentId, workItem.WorkItemId],
                Timeline:
                [
                    BuildEvent(
                        status: mappedStatus,
                        summary: $"Crash incident {incident.IncidentId} created a support case.",
                        occurredAtUtc: now,
                        actor: SupportCaseSourceKinds.DesktopCrash,
                        metadata: BuildMetadata(
                            ("work_item_id", workItem.WorkItemId),
                            ("crash_fingerprint", cluster.CrashFingerprint),
                            ("occurrence_count", cluster.OccurrenceCount.ToString(System.Globalization.CultureInfo.InvariantCulture))))
                ]);

            _store.CasesById[caseId] = created;
            _store.CaseIdByClusterKey[clusterKey] = caseId;
            _store.CrashCaseIdByWorkItemId[workItem.WorkItemId] = caseId;
            _store.PersistLocked();
            return created;
        }
    }

    public SupportCaseProjection? GetForReporter(string caseId, string? reporterUserId, string? reporterSubjectId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(caseId);

        lock (_store.Gate)
        {
            if (!_store.CasesById.TryGetValue(caseId.Trim(), out SupportCaseProjection? item))
            {
                return null;
            }

            return MatchesIdentity(item.ReporterUserId, item.ReporterSubjectId, reporterUserId, reporterSubjectId)
                ? item
                : null;
        }
    }

    public SupportCaseListResponse ListForReporter(string? reporterUserId, string? reporterSubjectId, string? status = null, string? kind = null)
    {
        lock (_store.Gate)
        {
            IEnumerable<SupportCaseProjection> items = _store.CasesById.Values
                .Where(item => MatchesIdentity(item.ReporterUserId, item.ReporterSubjectId, reporterUserId, reporterSubjectId));
            items = ApplyFilters(items, status, kind, candidateOwnerRepo: null, designImpactOnly: null);
            List<SupportCaseProjection> ordered = OrderCases(items);
            return new SupportCaseListResponse(ordered, ordered.Count);
        }
    }

    public SupportCaseListResponse ListForAutomation(
        string? status = null,
        string? kind = null,
        string? candidateOwnerRepo = null,
        bool? designImpactOnly = null)
    {
        lock (_store.Gate)
        {
            IEnumerable<SupportCaseProjection> items = _store.CasesById.Values;
            items = ApplyFilters(items, status, kind, candidateOwnerRepo, designImpactOnly);
            List<SupportCaseProjection> ordered = OrderCases(items);
            return new SupportCaseListResponse(ordered, ordered.Count);
        }
    }

    public SupportCaseProjection Transition(string caseId, SupportCaseTransitionRequest request)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(caseId);
        ArgumentNullException.ThrowIfNull(request);

        string targetStatus = NormalizeStatus(request.TargetStatus);
        if (string.Equals(targetStatus, SupportCaseStatuses.UserNotified, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException("Use the notification hook to move a support case into user_notified.");
        }
        string? note = NormalizeOptional(request.Note, 160);
        string? fixedVersion = NormalizeOptional(request.FixedVersion, 64);
        string? fixedChannel = NormalizeOptional(request.FixedChannel, 64);
        string? actor = NormalizeOptional(request.Actor, 64) ?? SupportCaseSourceKinds.FleetAutomation;
        DateTimeOffset now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            if (!_store.CasesById.TryGetValue(caseId.Trim(), out SupportCaseProjection? existing))
            {
                throw new KeyNotFoundException($"Unknown support case: {caseId}");
            }

            SupportCaseProjection updated = existing with
            {
                Status = targetStatus,
                UpdatedAtUtc = now,
                FixedVersion = fixedVersion ?? existing.FixedVersion,
                FixedChannel = fixedChannel ?? existing.FixedChannel,
                ReleasedToReporterChannelAtUtc = targetStatus == SupportCaseStatuses.ReleasedToReporterChannel
                    ? now
                    : existing.ReleasedToReporterChannelAtUtc,
                Timeline = AppendTimeline(
                    existing.Timeline,
                    BuildEvent(
                        status: targetStatus,
                        summary: note ?? $"Support case moved to {targetStatus}.",
                        occurredAtUtc: now,
                        actor: actor,
                        metadata: BuildMetadata(
                            ("fixed_version", fixedVersion),
                            ("fixed_channel", fixedChannel))))
            };
            _store.CasesById[updated.CaseId] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    public SupportCaseProjection RecordNotification(string caseId, SupportCaseNotificationRequest request)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(caseId);
        ArgumentNullException.ThrowIfNull(request);

        string note = NormalizeRequired(request.Note, nameof(request.Note), 160);
        string? actor = NormalizeOptional(request.Actor, 64) ?? SupportCaseSourceKinds.FleetAutomation;
        string? channel = NormalizeOptional(request.Channel, 64);
        DateTimeOffset now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            if (!_store.CasesById.TryGetValue(caseId.Trim(), out SupportCaseProjection? existing))
            {
                throw new KeyNotFoundException($"Unknown support case: {caseId}");
            }

            if (!string.Equals(existing.Status, SupportCaseStatuses.ReleasedToReporterChannel, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(existing.Status, SupportCaseStatuses.Deferred, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(existing.Status, SupportCaseStatuses.Rejected, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException(
                    "Support cases may only send user-facing notifications after release-to-reporter-channel, deferral, or rejection.");
            }

            SupportCaseProjection updated = existing with
            {
                Status = SupportCaseStatuses.UserNotified,
                UpdatedAtUtc = now,
                UserNotifiedAtUtc = now,
                Timeline = AppendTimeline(
                    existing.Timeline,
                    BuildEvent(
                        status: SupportCaseStatuses.UserNotified,
                        summary: note,
                        occurredAtUtc: now,
                        actor: actor,
                        metadata: BuildMetadata(("channel", channel))))
            };
            _store.CasesById[updated.CaseId] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    private static IEnumerable<SupportCaseProjection> ApplyFilters(
        IEnumerable<SupportCaseProjection> items,
        string? status,
        string? kind,
        string? candidateOwnerRepo,
        bool? designImpactOnly)
    {
        string? normalizedStatus = NormalizeOptional(status, 64);
        string? normalizedKind = NormalizeOptional(kind, 64);
        string? normalizedOwnerRepo = NormalizeOptional(candidateOwnerRepo, 64);

        if (normalizedStatus is not null)
        {
            items = items.Where(item => string.Equals(item.Status, normalizedStatus, StringComparison.OrdinalIgnoreCase));
        }

        if (normalizedKind is not null)
        {
            items = items.Where(item => string.Equals(item.Kind, normalizedKind, StringComparison.OrdinalIgnoreCase));
        }

        if (normalizedOwnerRepo is not null)
        {
            items = items.Where(item => string.Equals(item.CandidateOwnerRepo, normalizedOwnerRepo, StringComparison.OrdinalIgnoreCase));
        }

        if (designImpactOnly == true)
        {
            items = items.Where(static item => item.DesignImpactSuspected);
        }

        return items;
    }

    private static List<SupportCaseProjection> OrderCases(IEnumerable<SupportCaseProjection> items)
        => items
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ThenBy(static item => item.CaseId, StringComparer.OrdinalIgnoreCase)
            .ToList();

    private static SupportCaseTimelineEvent[] AppendTimeline(
        IReadOnlyList<SupportCaseTimelineEvent>? existing,
        SupportCaseTimelineEvent next)
    {
        List<SupportCaseTimelineEvent> items = existing?.ToList() ?? new List<SupportCaseTimelineEvent>();
        items.Add(next);
        return items
            .OrderBy(static item => item.OccurredAtUtc)
            .ThenBy(static item => item.EventId, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static SupportCaseTimelineEvent BuildEvent(
        string status,
        string summary,
        DateTimeOffset occurredAtUtc,
        string? actor,
        IReadOnlyDictionary<string, string>? metadata)
        => new(
            EventId: $"support_evt_{NewIdFragment()}",
            Status: status,
            Summary: summary,
            OccurredAtUtc: occurredAtUtc,
            Actor: actor,
            Metadata: metadata);

    private static IReadOnlyDictionary<string, string>? BuildMetadata(params (string key, string? value)[] items)
    {
        Dictionary<string, string> metadata = new(StringComparer.OrdinalIgnoreCase);
        foreach ((string key, string? value) in items)
        {
            string? normalized = NormalizeOptional(value, 256);
            if (normalized is null)
            {
                continue;
            }

            metadata[key] = normalized;
        }

        return metadata.Count == 0 ? null : metadata;
    }

    private static string BuildCrashDetail(
        CrashIncidentProjection incident,
        CrashClusterProjection cluster,
        CrashWorkItemProjection workItem)
        => string.Join(
            "\n",
            new[]
            {
                $"Crash fingerprint: {cluster.CrashFingerprint}",
                $"Exception: {incident.Envelope.ExceptionType}",
                $"Message: {incident.Envelope.ExceptionMessage}",
                $"Candidate owner repo: {workItem.CandidateOwnerRepo}",
                $"Occurrence count: {cluster.OccurrenceCount.ToString(System.Globalization.CultureInfo.InvariantCulture)}",
                $"Application version: {incident.Envelope.ApplicationVersion}",
                $"Channel: {incident.RegistryContext.ReleaseChannel ?? "unknown"}",
                $"Platform: {incident.RegistryContext.Platform ?? incident.Envelope.OperatingSystem}",
                "",
                incident.Envelope.ExceptionDetail
            });

    private static string MapCrashStatus(string crashStatus)
        => crashStatus.Trim().ToLowerInvariant() switch
        {
            "escalated" => SupportCaseStatuses.Routed,
            "triage_required" => SupportCaseStatuses.Clustered,
            _ => SupportCaseStatuses.New
        };

    private static bool MatchesIdentity(string? storedUserId, string? storedSubjectId, string? requestedUserId, string? requestedSubjectId)
    {
        string? normalizedUserId = NormalizeOptional(requestedUserId, 64);
        string? normalizedSubjectId = NormalizeOptional(requestedSubjectId, 128);
        if (normalizedUserId is null && normalizedSubjectId is null)
        {
            return false;
        }

        return (normalizedUserId is not null && string.Equals(storedUserId, normalizedUserId, StringComparison.OrdinalIgnoreCase))
               || (normalizedSubjectId is not null && string.Equals(storedSubjectId, normalizedSubjectId, StringComparison.OrdinalIgnoreCase));
    }

    private static string ResolveCandidateOwnerRepo(
        string kind,
        string title,
        string summary,
        string detail,
        string? headId,
        string? platform,
        string? installationId,
        bool designImpact)
    {
        string probe = string.Join("\n", new[] { title, summary, detail, headId, platform });
        if (kind == SupportCaseKinds.CrashReport)
        {
            return "chummer6-ui";
        }

        if (kind == SupportCaseKinds.InstallHelp
            || probe.Contains("download", StringComparison.OrdinalIgnoreCase)
            || probe.Contains("install", StringComparison.OrdinalIgnoreCase)
            || probe.Contains("update", StringComparison.OrdinalIgnoreCase)
            || probe.Contains("account", StringComparison.OrdinalIgnoreCase)
            || probe.Contains("channel", StringComparison.OrdinalIgnoreCase))
        {
            return "chummer6-hub";
        }

        if (kind == SupportCaseKinds.BugReport)
        {
            return "chummer6-ui";
        }

        return designImpact ? "chummer6-design" : "chummer6-hub";
    }

    private static bool LooksLikeDesignImpact(string title, string summary, string detail)
    {
        string probe = $"{title}\n{summary}\n{detail}";
        return probe.Contains("copy", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("confusing", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("policy", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("docs", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("documentation", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("promise", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("landing", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("guide", StringComparison.OrdinalIgnoreCase)
               || probe.Contains("wording", StringComparison.OrdinalIgnoreCase);
    }

    private static string ComputeClusterKey(
        string kind,
        string title,
        string summary,
        string? reporterEmail,
        string? userId,
        string? subjectId,
        string? installationId,
        string? applicationVersion,
        string? releaseChannel,
        string? headId,
        string candidateOwnerRepo)
    {
        string seed = string.Join(
            "|",
            new[]
            {
                kind,
                title.Trim().ToLowerInvariant(),
                summary.Trim().ToLowerInvariant(),
                NormalizeOptional(reporterEmail, 256) ?? "-",
                NormalizeOptional(userId, 64) ?? "-",
                NormalizeOptional(subjectId, 128) ?? "-",
                NormalizeOptional(installationId, 64) ?? "-",
                NormalizeOptional(applicationVersion, 64) ?? "-",
                NormalizeOptional(releaseChannel, 64) ?? "-",
                NormalizeOptional(headId, 64) ?? "-",
                candidateOwnerRepo
            });
        return $"support:{ComputeHash(seed)}";
    }

    private static string ComputeHash(string value)
    {
        byte[] input = Encoding.UTF8.GetBytes(value);
        byte[] hash = SHA256.HashData(input);
        return Convert.ToHexString(hash[..8]).ToLowerInvariant();
    }

    private static string NormalizeKind(string value)
    {
        string normalized = NormalizeRequired(value, nameof(value), 64).ToLowerInvariant();
        if (!AllowedKinds.Contains(normalized))
        {
            throw new ArgumentException($"Unsupported support case kind: {value}", nameof(value));
        }

        return normalized;
    }

    private static string NormalizeStatus(string value)
    {
        string normalized = NormalizeRequired(value, nameof(value), 64).ToLowerInvariant();
        if (!AllowedStatuses.Contains(normalized))
        {
            throw new ArgumentException($"Unsupported support case status: {value}", nameof(value));
        }

        return normalized;
    }

    private static string NormalizeSource(string? value)
    {
        string? normalized = NormalizeOptional(value, 64);
        if (normalized is null)
        {
            return SupportCaseSourceKinds.HubAccount;
        }
        normalized = normalized.ToLowerInvariant();
        return normalized switch
        {
            SupportCaseSourceKinds.HubAccount => normalized,
            SupportCaseSourceKinds.DesktopCrash => normalized,
            SupportCaseSourceKinds.DesktopFeedback => normalized,
            SupportCaseSourceKinds.PublicWeb => normalized,
            SupportCaseSourceKinds.FleetAutomation => normalized,
            _ => SupportCaseSourceKinds.HubAccount
        };
    }

    private static string NormalizeRequired(string value, string parameterName, int maxLength)
    {
        string? normalized = NormalizeOptional(value, maxLength);
        return normalized ?? throw new ArgumentException($"{parameterName} is required.", parameterName);
    }

    private static string? NormalizeOptional(string? value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        return normalized.Length <= maxLength ? normalized : normalized[..maxLength];
    }

    private static string NewIdFragment() => Guid.NewGuid().ToString("N")[..12];
}
