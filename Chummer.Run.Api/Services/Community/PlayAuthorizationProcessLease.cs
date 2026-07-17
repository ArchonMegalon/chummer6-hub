namespace Chummer.Run.Api.Services.Community;

/// <summary>
/// Holds an exclusive OS file handle for the full enabled-host lifetime. The lock file is
/// anchored beside the normalized CommunityStore snapshot so two local host/service-provider
/// instances cannot both activate the whole-snapshot Play authorization writer.
/// </summary>
public sealed class PlayAuthorizationProcessLease : IHostedService, IDisposable
{
    private readonly object _gate = new();
    private readonly bool _enabled;
    private FileStream? _lease;
    private bool _disposed;

    public PlayAuthorizationProcessLease(IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        _enabled = configuration.GetValue(PlayAuthorizationApiPolicy.FeatureConfigurationKey, false);
        if (!_enabled)
        {
            return;
        }

        string storagePath = CommunityStore.ResolveStoragePath(configuration);
        string leasePath = $"{storagePath}.play-authorization.lease";
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(leasePath)!);
            _lease = new FileStream(
                leasePath,
                FileMode.OpenOrCreate,
                FileAccess.ReadWrite,
                FileShare.None,
                bufferSize: 1,
                FileOptions.WriteThrough);
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or NotSupportedException)
        {
            _lease?.Dispose();
            _lease = null;
            throw new InvalidOperationException(
                "Play authorization activation could not acquire its exclusive CommunityStore writer lease.",
                exception);
        }
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        lock (_gate)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_enabled && _lease is null)
            {
                throw new InvalidOperationException(
                    "Play authorization activation does not hold its exclusive CommunityStore writer lease.");
            }
        }

        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken)
    {
        Dispose();
        return Task.CompletedTask;
    }

    public void Dispose()
    {
        lock (_gate)
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
            _lease?.Dispose();
            _lease = null;
        }
    }
}

public static class PlayAuthorizationProcessLeaseServiceCollectionExtensions
{
    public static IServiceCollection AddPlayAuthorizationProcessLease(this IServiceCollection services)
    {
        ArgumentNullException.ThrowIfNull(services);
        services.AddSingleton<PlayAuthorizationProcessLease>();
        services.AddSingleton<IHostedService>(static provider =>
            provider.GetRequiredService<PlayAuthorizationProcessLease>());
        return services;
    }
}
