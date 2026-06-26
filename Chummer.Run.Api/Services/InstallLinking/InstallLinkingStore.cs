using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkingStore
{
    private readonly ILogger<InstallLinkingStore> _logger;
    private readonly string _storagePath;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    public InstallLinkingStore(IConfiguration configuration, ILogger<InstallLinkingStore> logger)
    {
        _logger = logger;
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public object Gate { get; } = new();
    public string StoragePath => _storagePath;
    public Dictionary<string, DownloadReceiptDto> ReceiptsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, InstallClaimTicketDto> ClaimTicketsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, InstallBrowserCallbackDto> BrowserCallbacksById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, ClaimedInstallationDto> InstallationsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, InstallationGrantDto> GrantsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PersonalizedInstallScriptLinkDto> PersonalizedInstallScriptsById { get; } = new(StringComparer.OrdinalIgnoreCase);

    public void PersistLocked()
    {
        var snapshot = new InstallLinkingStoreSnapshot(
            Receipts: ReceiptsById.Values
                .OrderByDescending(static item => item.IssuedAtUtc)
                .ToArray(),
            ClaimTickets: ClaimTicketsById.Values
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            BrowserCallbacks: BrowserCallbacksById.Values
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray(),
            Installations: InstallationsById.Values
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray(),
            Grants: GrantsById.Values
                .OrderByDescending(static item => item.IssuedAtUtc)
                .ToArray(),
            PersonalizedInstallScripts: PersonalizedInstallScriptsById.Values
                .OrderByDescending(static item => item.IssuedAtUtc)
                .ToArray());

        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        var tempPath = $"{_storagePath}.tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, _jsonOptions), System.Text.Encoding.UTF8);
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (Gate)
        {
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("InstallLinkingStore starting empty at {StoragePath}.", _storagePath);
                return;
            }

            try
            {
                var snapshotJson = File.ReadAllText(_storagePath, System.Text.Encoding.UTF8);
                var snapshot = JsonSerializer.Deserialize<InstallLinkingStoreSnapshot>(snapshotJson, _jsonOptions)
                    ?? throw new InvalidOperationException($"Unable to deserialize install-linking snapshot: {_storagePath}");

                ApplySnapshotLocked(snapshot);
                _logger.LogInformation(
                    "InstallLinkingStore loaded {ReceiptCount} receipts, {TicketCount} claim tickets, {InstallCount} claimed installs, and {ScriptCount} personalized install scripts from {StoragePath}.",
                    ReceiptsById.Count,
                    ClaimTicketsById.Count,
                    InstallationsById.Count,
                    PersonalizedInstallScriptsById.Count,
                    _storagePath);
            }
            catch (JsonException ex)
            {
                ApplySnapshotLocked(new InstallLinkingStoreSnapshot([], [], [], [], [], []));
                QuarantineCorruptStoreFile();
                _logger.LogWarning(ex, "InstallLinkingStore quarantined corrupt durable state at {StoragePath} and restarted empty.", _storagePath);
            }
        }
    }

    private void QuarantineCorruptStoreFile()
    {
        string quarantinePath = $"{_storagePath}.corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}";
        try
        {
            File.Move(_storagePath, quarantinePath);
        }
        catch
        {
            // Starting empty is safer than crashing when a local install-linking store file is unreadable.
        }
    }

    private void ApplySnapshotLocked(InstallLinkingStoreSnapshot snapshot)
    {
        ReceiptsById.Clear();
        ClaimTicketsById.Clear();
        BrowserCallbacksById.Clear();
        InstallationsById.Clear();
        GrantsById.Clear();
        PersonalizedInstallScriptsById.Clear();

        foreach (var receipt in snapshot.Receipts ?? Array.Empty<DownloadReceiptDto>())
        {
            ReceiptsById[receipt.ReceiptId] = receipt;
        }

        foreach (var ticket in snapshot.ClaimTickets ?? Array.Empty<InstallClaimTicketDto>())
        {
            ClaimTicketsById[ticket.TicketId] = ticket;
        }

        foreach (var callback in snapshot.BrowserCallbacks ?? Array.Empty<InstallBrowserCallbackDto>())
        {
            BrowserCallbacksById[callback.CallbackId] = callback;
        }

        foreach (var installation in snapshot.Installations ?? Array.Empty<ClaimedInstallationDto>())
        {
            InstallationsById[installation.InstallationId] = installation;
        }

        foreach (var grant in snapshot.Grants ?? Array.Empty<InstallationGrantDto>())
        {
            GrantsById[grant.GrantId] = grant;
        }

        foreach (var script in snapshot.PersonalizedInstallScripts ?? Array.Empty<PersonalizedInstallScriptLinkDto>())
        {
            PersonalizedInstallScriptsById[script.ScriptId] = script;
        }
    }

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        var configured = configuration["CHUMMER_INSTALL_LINKING_STORE_PATH"] ?? configuration["InstallLinking:StorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "install-linking-store.json");
    }
}

internal sealed record InstallLinkingStoreSnapshot(
    IReadOnlyList<DownloadReceiptDto> Receipts,
    IReadOnlyList<InstallClaimTicketDto> ClaimTickets,
    IReadOnlyList<InstallBrowserCallbackDto>? BrowserCallbacks,
    IReadOnlyList<ClaimedInstallationDto> Installations,
    IReadOnlyList<InstallationGrantDto> Grants,
    IReadOnlyList<PersonalizedInstallScriptLinkDto>? PersonalizedInstallScripts = null);
