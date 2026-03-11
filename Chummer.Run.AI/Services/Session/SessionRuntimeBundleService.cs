using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Session;

public interface ISessionRuntimeBundleService
{
    SessionRuntimeBundleDto ResolveBundle(string sessionId, string sceneId);
}

public sealed class SessionRuntimeBundleService : ISessionRuntimeBundleService
{
    private static readonly string[] DefaultSupportedExchangeFormats =
    [
        "session-ledger.v1",
        "session-runtime-bundle.v1",
        "foundry-vtt.scene-ledger.v1"
    ];

    private sealed class BundleState
    {
        public int ProjectionVersion { get; set; }
        public string ProjectionFingerprint { get; set; } = "empty";
        public DateTimeOffset GeneratedAtUtc { get; set; }
        public string BundleVersion { get; set; } = "bundle-0";
        public string[] InvalidationSignals { get; set; } = Array.Empty<string>();
        public string[] IncludedEventTypes { get; set; } = Array.Empty<string>();
        public bool OfflineCapable { get; set; } = true;
        public string CollaborationMode { get; set; } = "local-first";
        public string[] SupportedExchangeFormats { get; set; } = DefaultSupportedExchangeFormats;
    }

    private readonly ConcurrentDictionary<string, BundleState> _bundles = new();
    private readonly ISessionLedgerService _ledger;

    public SessionRuntimeBundleService(ISessionLedgerService ledger)
    {
        _ledger = ledger;
    }

    public SessionRuntimeBundleDto ResolveBundle(string sessionId, string sceneId)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sceneId))
        {
            return new SessionRuntimeBundleDto(
                SessionId: sessionId ?? string.Empty,
                SceneId: sceneId ?? string.Empty,
                BundleVersion: "bundle-0",
                Ready: false,
                ProjectionVersion: 0,
                ProjectionFingerprint: "empty",
                GeneratedAtUtc: DateTimeOffset.UtcNow,
                InvalidationSignals: Array.Empty<string>(),
                IncludedEventTypes: Array.Empty<string>(),
                OfflineCapable: true,
                CollaborationMode: "local-first",
                SupportedExchangeFormats: DefaultSupportedExchangeFormats);
        }

        var projection = _ledger.GetProjection(sessionId, sceneId);
        var key = ComposeKey(sessionId, sceneId);
        var invalidationSignals = BuildInvalidationSignals(sessionId, sceneId, projection.Version);
        var includedEventTypes = projection.Events
            .Select(evt => evt.EventType)
            .Where(evt => !string.IsNullOrWhiteSpace(evt))
            .Distinct(StringComparer.Ordinal)
            .OrderBy(evt => evt, StringComparer.Ordinal)
            .ToArray();

        if (projection.Events.Count == 0)
        {
            _bundles[key] = new BundleState
            {
                ProjectionVersion = 0,
                ProjectionFingerprint = projection.ProjectionFingerprint,
                GeneratedAtUtc = DateTimeOffset.UtcNow,
                BundleVersion = "bundle-empty",
                InvalidationSignals = invalidationSignals,
                IncludedEventTypes = Array.Empty<string>(),
                OfflineCapable = true,
                CollaborationMode = "local-first",
                SupportedExchangeFormats = DefaultSupportedExchangeFormats
            };

            return new SessionRuntimeBundleDto(
                SessionId: sessionId,
                SceneId: sceneId,
                BundleVersion: "bundle-empty",
                Ready: false,
                ProjectionVersion: 0,
                ProjectionFingerprint: projection.ProjectionFingerprint,
                GeneratedAtUtc: _bundles[key].GeneratedAtUtc,
                InvalidationSignals: invalidationSignals,
                IncludedEventTypes: Array.Empty<string>(),
                OfflineCapable: true,
                CollaborationMode: "local-first",
                SupportedExchangeFormats: DefaultSupportedExchangeFormats);
        }

        var bundleVersion = $"bundle-{projection.Version}-{projection.ProjectionFingerprint[..8]}";
        var state = _bundles.AddOrUpdate(
            key,
            _ => new BundleState
            {
                ProjectionVersion = projection.Version,
                ProjectionFingerprint = projection.ProjectionFingerprint,
                GeneratedAtUtc = DateTimeOffset.UtcNow,
                BundleVersion = bundleVersion,
                InvalidationSignals = invalidationSignals,
                IncludedEventTypes = includedEventTypes,
                OfflineCapable = true,
                CollaborationMode = "local-first",
                SupportedExchangeFormats = DefaultSupportedExchangeFormats
            },
            (_, existing) =>
            {
                if (string.Equals(existing.ProjectionFingerprint, projection.ProjectionFingerprint, StringComparison.Ordinal))
                {
                    existing.ProjectionVersion = projection.Version;
                    existing.InvalidationSignals = invalidationSignals;
                    existing.IncludedEventTypes = includedEventTypes;
                    existing.OfflineCapable = true;
                    existing.CollaborationMode = "local-first";
                    existing.SupportedExchangeFormats = DefaultSupportedExchangeFormats;
                    return existing;
                }

                existing.ProjectionVersion = projection.Version;
                existing.ProjectionFingerprint = projection.ProjectionFingerprint;
                existing.GeneratedAtUtc = DateTimeOffset.UtcNow;
                existing.BundleVersion = bundleVersion;
                existing.InvalidationSignals = invalidationSignals;
                existing.IncludedEventTypes = includedEventTypes;
                existing.OfflineCapable = true;
                existing.CollaborationMode = "local-first";
                existing.SupportedExchangeFormats = DefaultSupportedExchangeFormats;
                return existing;
            });

        return new SessionRuntimeBundleDto(
            SessionId: sessionId,
            SceneId: sceneId,
            BundleVersion: state.BundleVersion,
            Ready: true,
            ProjectionVersion: state.ProjectionVersion,
            ProjectionFingerprint: state.ProjectionFingerprint,
            GeneratedAtUtc: state.GeneratedAtUtc,
            InvalidationSignals: state.InvalidationSignals,
            IncludedEventTypes: state.IncludedEventTypes,
            OfflineCapable: state.OfflineCapable,
            CollaborationMode: state.CollaborationMode,
            SupportedExchangeFormats: state.SupportedExchangeFormats);
    }

    private static string[] BuildInvalidationSignals(string sessionId, string sceneId, int projectionVersion)
    {
        return
        [
            $"event-stream:{sessionId}:{sceneId}",
            $"session:{sessionId}",
            $"scene:{sceneId}",
            $"projection-version:{projectionVersion}"
        ];
    }

    private static string ComposeKey(string sessionId, string sceneId) => $"{sessionId}::{sceneId}";
}
