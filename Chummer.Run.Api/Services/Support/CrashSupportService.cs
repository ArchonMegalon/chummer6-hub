using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Control.Contracts.Support;
using Microsoft.Extensions.Logging;

namespace Chummer.Run.Api.Services.Support;

public sealed class CrashSupportService
{
    private readonly SupportStore _store;
    private readonly SupportCaseService _supportCases;
    private readonly InstallLinkingService _installLinking;
    private readonly ILogger<CrashSupportService> _logger;

    public CrashSupportService(
        SupportStore store,
        SupportCaseService supportCases,
        InstallLinkingService installLinking,
        ILogger<CrashSupportService> logger)
    {
        _store = store;
        _supportCases = supportCases;
        _installLinking = installLinking;
        _logger = logger;
    }

    public CrashIntakeAcceptedResponse Submit(CrashEnvelope envelope)
    {
        ArgumentNullException.ThrowIfNull(envelope);

        lock (_store.Gate)
        {
            string normalizedCrashId = NormalizeRequired(envelope.CrashId, nameof(envelope.CrashId));
            if (_store.IncidentIdByCrashId.TryGetValue(normalizedCrashId, out string? existingIncidentId)
                && _store.IncidentsById.TryGetValue(existingIncidentId, out CrashIncidentProjection? existingIncident))
            {
                CrashClusterProjection existingCluster = _store.ClustersById[existingIncident.ClusterId];
                CrashWorkItemProjection existingWorkItem = _store.WorkItemsById[existingIncident.WorkItemId];
                return new CrashIntakeAcceptedResponse(
                    Incident: existingIncident,
                    Cluster: existingCluster,
                    WorkItem: existingWorkItem,
                    ForwardedForAutomation: true);
            }

            DateTimeOffset receivedAtUtc = DateTimeOffset.UtcNow;
            CrashEnvelope normalizedEnvelope = NormalizeEnvelope(envelope);
            normalizedEnvelope = ResolveTrustedReporter(normalizedEnvelope);
            CrashRegistryContextProjection registryContext = BuildRegistryContext(normalizedEnvelope);
            string clusterId = GetOrCreateClusterIdLocked(normalizedEnvelope.CrashFingerprint);
            string workItemId = GetOrCreateWorkItemIdLocked(clusterId);
            string incidentId = $"crash_inc_{normalizedCrashId}";

            CrashIncidentProjection incident = new(
                IncidentId: incidentId,
                ClusterId: clusterId,
                WorkItemId: workItemId,
                ReceivedAtUtc: receivedAtUtc,
                UpdatedAtUtc: receivedAtUtc,
                Status: "queued_for_triage",
                Envelope: normalizedEnvelope,
                RegistryContext: registryContext);

            CrashClusterProjection cluster = MergeCluster(
                _store.ClustersById.GetValueOrDefault(clusterId),
                incident);
            CrashWorkItemProjection workItem = MergeWorkItem(
                _store.WorkItemsById.GetValueOrDefault(workItemId),
                cluster,
                incident,
                registryContext);

            _store.IncidentsById[incidentId] = incident;
            _store.IncidentIdByCrashId[normalizedCrashId] = incidentId;
            _store.ClustersById[clusterId] = cluster;
            _store.WorkItemsById[workItemId] = workItem;
            _supportCases.UpsertFromCrash(incident, cluster, workItem);
            _store.PersistLocked();

            _logger.LogInformation(
                "Accepted crash incident {IncidentId} into cluster {ClusterId} / work item {WorkItemId}.",
                incidentId,
                clusterId,
                workItemId);

            return new CrashIntakeAcceptedResponse(
                Incident: incident,
                Cluster: cluster,
                WorkItem: workItem,
                ForwardedForAutomation: true);
        }
    }

    public CrashIncidentProjection? GetIncident(string incidentId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(incidentId);
        lock (_store.Gate)
        {
            return _store.IncidentsById.GetValueOrDefault(incidentId.Trim());
        }
    }

    public CrashClusterListResponse ListClusters(string? status = null, string? fingerprint = null)
    {
        lock (_store.Gate)
        {
            IEnumerable<CrashClusterProjection> items = _store.ClustersById.Values;
            if (!string.IsNullOrWhiteSpace(status))
            {
                items = items.Where(item => string.Equals(item.Status, status.Trim(), StringComparison.OrdinalIgnoreCase));
            }

            if (!string.IsNullOrWhiteSpace(fingerprint))
            {
                items = items.Where(item => string.Equals(item.CrashFingerprint, fingerprint.Trim(), StringComparison.OrdinalIgnoreCase));
            }

            List<CrashClusterProjection> ordered = items
                .OrderByDescending(item => item.LastSeenAtUtc)
                .ThenBy(item => item.ClusterId, StringComparer.OrdinalIgnoreCase)
                .ToList();
            return new CrashClusterListResponse(ordered, ordered.Count);
        }
    }

    public CrashWorkItemListResponse ListWorkItems(string? status = null, string? candidateOwnerRepo = null)
    {
        lock (_store.Gate)
        {
            IEnumerable<CrashWorkItemProjection> items = _store.WorkItemsById.Values;
            if (!string.IsNullOrWhiteSpace(status))
            {
                items = items.Where(item => string.Equals(item.Status, status.Trim(), StringComparison.OrdinalIgnoreCase));
            }

            if (!string.IsNullOrWhiteSpace(candidateOwnerRepo))
            {
                items = items.Where(item => string.Equals(item.CandidateOwnerRepo, candidateOwnerRepo.Trim(), StringComparison.OrdinalIgnoreCase));
            }

            List<CrashWorkItemProjection> ordered = items
                .OrderByDescending(item => item.LastSeenAtUtc)
                .ThenBy(item => item.WorkItemId, StringComparer.OrdinalIgnoreCase)
                .ToList();
            return new CrashWorkItemListResponse(ordered, ordered.Count);
        }
    }

    private string GetOrCreateClusterIdLocked(string crashFingerprint)
    {
        string normalizedFingerprint = NormalizeRequired(crashFingerprint, nameof(crashFingerprint));
        if (_store.ClusterIdByFingerprint.TryGetValue(normalizedFingerprint, out string? existingClusterId))
        {
            return existingClusterId;
        }

        string clusterId = $"crash_cluster_{ComputeHash(normalizedFingerprint)}";
        _store.ClusterIdByFingerprint[normalizedFingerprint] = clusterId;
        return clusterId;
    }

    private string GetOrCreateWorkItemIdLocked(string clusterId)
    {
        if (_store.WorkItemIdByClusterId.TryGetValue(clusterId, out string? existingWorkItemId))
        {
            return existingWorkItemId;
        }

        string workItemId = $"crash_work_{ComputeHash(clusterId)}";
        _store.WorkItemIdByClusterId[clusterId] = workItemId;
        return workItemId;
    }

    private static CrashEnvelope NormalizeEnvelope(CrashEnvelope envelope)
        => envelope with
        {
            CrashId = NormalizeRequired(envelope.CrashId, nameof(envelope.CrashId)),
            HeadId = NormalizeRequired(envelope.HeadId, nameof(envelope.HeadId)),
            ApplicationVersion = NormalizeRequired(envelope.ApplicationVersion, nameof(envelope.ApplicationVersion)),
            RuntimeVersion = NormalizeRequired(envelope.RuntimeVersion, nameof(envelope.RuntimeVersion)),
            OperatingSystem = NormalizeRequired(envelope.OperatingSystem, nameof(envelope.OperatingSystem)),
            ProcessArchitecture = NormalizeRequired(envelope.ProcessArchitecture, nameof(envelope.ProcessArchitecture)),
            CrashFingerprint = NormalizeRequired(envelope.CrashFingerprint, nameof(envelope.CrashFingerprint)),
            ExceptionType = NormalizeRequired(envelope.ExceptionType, nameof(envelope.ExceptionType)),
            ExceptionMessage = NormalizeRequired(envelope.ExceptionMessage, nameof(envelope.ExceptionMessage)),
            ExceptionDetail = NormalizeRequired(envelope.ExceptionDetail, nameof(envelope.ExceptionDetail)),
            ReleaseChannel = NormalizeOptional(envelope.ReleaseChannel),
            Platform = NormalizeOptional(envelope.Platform),
            DesktopHead = NormalizeOptional(envelope.DesktopHead),
            RuntimeHead = NormalizeOptional(envelope.RuntimeHead),
            InstallationId = NormalizeOptional(envelope.InstallationId),
            InstallationGrantToken = NormalizeOptional(envelope.InstallationGrantToken),
            UserId = NormalizeOptional(envelope.UserId),
            SubjectId = NormalizeOptional(envelope.SubjectId),
            LastActionCategory = NormalizeOptional(envelope.LastActionCategory),
            LogTail = NormalizeLogTail(envelope.LogTail)
        };

    private CrashEnvelope ResolveTrustedReporter(CrashEnvelope envelope)
    {
        if (string.IsNullOrWhiteSpace(envelope.InstallationId) || string.IsNullOrWhiteSpace(envelope.InstallationGrantToken))
        {
            return ClearReporterIdentity(envelope);
        }

        var installation = _installLinking.ResolveInstallationForGrant(envelope.InstallationId, envelope.InstallationGrantToken);
        if (installation is null)
        {
            return ClearReporterIdentity(envelope);
        }

        return envelope with
        {
            InstallationId = NormalizeOptional(installation.InstallationId),
            UserId = NormalizeOptional(installation.UserId),
            SubjectId = NormalizeOptional(installation.SubjectId)
        };
    }

    private static CrashEnvelope ClearReporterIdentity(CrashEnvelope envelope)
        => envelope with
        {
            InstallationId = null,
            InstallationGrantToken = null,
            UserId = null,
            SubjectId = null
        };

    private static CrashRegistryContextProjection BuildRegistryContext(CrashEnvelope envelope)
        => new(
            ApplicationVersion: envelope.ApplicationVersion,
            ReleaseChannel: NormalizeOptional(envelope.ReleaseChannel) ?? "unknown",
            Platform: NormalizeOptional(envelope.Platform) ?? NormalizePlatformFromOs(envelope.OperatingSystem),
            ProcessArchitecture: envelope.ProcessArchitecture,
            DesktopHead: NormalizeOptional(envelope.DesktopHead) ?? envelope.HeadId,
            RuntimeHead: NormalizeOptional(envelope.RuntimeHead),
            UpdateAvailable: false,
            UpdateTargetVersion: null,
            Source: "hub-intake-envelope");

    private static CrashClusterProjection MergeCluster(CrashClusterProjection? current, CrashIncidentProjection incident)
    {
        HashSet<string> incidentIds = new(current?.IncidentIds ?? Array.Empty<string>(), StringComparer.OrdinalIgnoreCase)
        {
            incident.IncidentId
        };
        HashSet<string> versions = new(current?.ApplicationVersions ?? Array.Empty<string>(), StringComparer.OrdinalIgnoreCase)
        {
            incident.Envelope.ApplicationVersion
        };
        HashSet<string> channels = new(current?.ReleaseChannels ?? Array.Empty<string>(), StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(incident.RegistryContext.ReleaseChannel))
        {
            channels.Add(incident.RegistryContext.ReleaseChannel);
        }

        HashSet<string> platforms = new(current?.Platforms ?? Array.Empty<string>(), StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(incident.RegistryContext.Platform))
        {
            platforms.Add(incident.RegistryContext.Platform);
        }

        DateTimeOffset eventAtUtc = incident.Envelope.CapturedAtUtc == default ? incident.ReceivedAtUtc : incident.Envelope.CapturedAtUtc;
        int occurrenceCount = incidentIds.Count;
        bool regressionSuspected = versions.Count > 1 || occurrenceCount >= 3;
        string status = ResolveStatus(occurrenceCount, regressionSuspected);
        return new CrashClusterProjection(
            ClusterId: current?.ClusterId ?? incident.ClusterId,
            CrashFingerprint: incident.Envelope.CrashFingerprint,
            ExceptionType: incident.Envelope.ExceptionType,
            Status: status,
            OccurrenceCount: occurrenceCount,
            FirstSeenAtUtc: current is null || eventAtUtc < current.FirstSeenAtUtc ? eventAtUtc : current.FirstSeenAtUtc,
            LastSeenAtUtc: current is null || eventAtUtc > current.LastSeenAtUtc ? eventAtUtc : current.LastSeenAtUtc,
            IncidentIds: incidentIds.OrderBy(static item => item, StringComparer.OrdinalIgnoreCase).ToArray(),
            ApplicationVersions: versions.OrderBy(static item => item, StringComparer.OrdinalIgnoreCase).ToArray(),
            ReleaseChannels: channels.OrderBy(static item => item, StringComparer.OrdinalIgnoreCase).ToArray(),
            Platforms: platforms.OrderBy(static item => item, StringComparer.OrdinalIgnoreCase).ToArray());
    }

    private static CrashWorkItemProjection MergeWorkItem(
        CrashWorkItemProjection? current,
        CrashClusterProjection cluster,
        CrashIncidentProjection incident,
        CrashRegistryContextProjection registryContext)
    {
        HashSet<string> incidentIds = new(current?.IncidentIds ?? Array.Empty<string>(), StringComparer.OrdinalIgnoreCase)
        {
            incident.IncidentId
        };
        bool regressionSuspected = cluster.ApplicationVersions.Count > 1 || cluster.OccurrenceCount >= 3;
        return new CrashWorkItemProjection(
            WorkItemId: current?.WorkItemId ?? incident.WorkItemId,
            ClusterId: cluster.ClusterId,
            Status: ResolveStatus(cluster.OccurrenceCount, regressionSuspected),
            Summary: BuildSummary(incident, cluster),
            CandidateOwnerRepo: ResolveCandidateOwnerRepo(incident.Envelope),
            RegressionSuspected: regressionSuspected,
            OccurrenceCount: cluster.OccurrenceCount,
            FirstSeenAtUtc: cluster.FirstSeenAtUtc,
            LastSeenAtUtc: cluster.LastSeenAtUtc,
            RegistryContext: registryContext,
            IncidentIds: incidentIds.OrderBy(static item => item, StringComparer.OrdinalIgnoreCase).ToArray());
    }

    private static string BuildSummary(CrashIncidentProjection incident, CrashClusterProjection cluster)
    {
        string head = NormalizeOptional(incident.Envelope.DesktopHead) ?? incident.Envelope.HeadId;
        string platform = incident.RegistryContext.Platform ?? incident.Envelope.OperatingSystem;
        string channel = incident.RegistryContext.ReleaseChannel ?? "unknown";
        return $"{incident.Envelope.ExceptionType} on {head} ({platform}, {channel}) x{cluster.OccurrenceCount}";
    }

    private static string ResolveCandidateOwnerRepo(CrashEnvelope envelope)
    {
        string probe = string.Join('|',
            envelope.HeadId,
            envelope.DesktopHead,
            envelope.RuntimeHead,
            envelope.Platform);
        if (probe.Contains("hub", StringComparison.OrdinalIgnoreCase))
        {
            return "chummer6-hub";
        }

        return "chummer6-ui";
    }

    private static string ResolveStatus(int occurrenceCount, bool regressionSuspected)
    {
        if (regressionSuspected)
        {
            return "escalated";
        }

        return occurrenceCount > 1 ? "triage_required" : "new";
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string NormalizeRequired(string value, string parameterName)
    {
        string? normalized = NormalizeOptional(value);
        return normalized ?? throw new ArgumentException($"{parameterName} is required.", parameterName);
    }

    private static IReadOnlyList<string> NormalizeLogTail(IReadOnlyList<string>? logTail)
    {
        if (logTail is null || logTail.Count == 0)
        {
            return Array.Empty<string>();
        }

        return logTail
            .Where(static line => !string.IsNullOrWhiteSpace(line))
            .Select(static line => line.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(16)
            .ToArray();
    }

    private static string NormalizePlatformFromOs(string operatingSystem)
    {
        if (operatingSystem.Contains("windows", StringComparison.OrdinalIgnoreCase))
        {
            return "windows";
        }

        if (operatingSystem.Contains("darwin", StringComparison.OrdinalIgnoreCase)
            || operatingSystem.Contains("mac", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        if (operatingSystem.Contains("linux", StringComparison.OrdinalIgnoreCase))
        {
            return "linux";
        }

        return "unknown";
    }

    private static string ComputeHash(string value)
    {
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(bytes[..8]).ToLowerInvariant();
    }
}
