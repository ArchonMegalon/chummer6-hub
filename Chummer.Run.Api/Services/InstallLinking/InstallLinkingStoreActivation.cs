using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Hosting;
using Chummer.Run.Api.Services.InstallLinking.Postgres;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed record DataProtectionKeyProtectionStatus(bool Ready, string Code);

public sealed record InstallLinkingStoreReadiness(bool Ready, string Code);

public interface IInstallLinkingStoreReadinessProbe
{
    InstallLinkingStoreReadiness Evaluate();
}

public sealed record InstallLinkingRollbackAuthorityReadiness(bool Ready, string Code);

public interface IInstallLinkingRollbackAuthorityReadinessProbe
{
    InstallLinkingRollbackAuthorityReadiness Evaluate();
}

public sealed class UnavailableInstallLinkingRollbackAuthorityReadinessProbe
    : IInstallLinkingRollbackAuthorityReadinessProbe
{
    public InstallLinkingRollbackAuthorityReadiness Evaluate()
        => new(false, "external_rollback_authority_unimplemented");
}

public sealed class InstallLinkingStoreActivation : IInstallLinkingStoreReadinessProbe, IDisposable
{
    private readonly IConfiguration _configuration;
    private readonly IDataProtectionProvider _dataProtectionProvider;
    private readonly IHostEnvironment _environment;
    private readonly ILoggerFactory _loggerFactory;
    private readonly DataProtectionKeyProtectionStatus _keyProtection;
    private readonly InstallLinkingPostgresAuthorityCoordinator? _postgresAuthority;
    private readonly Lazy<ActivationResult> _activation;

    public InstallLinkingStoreActivation(
        IConfiguration configuration,
        IDataProtectionProvider dataProtectionProvider,
        IHostEnvironment environment,
        ILoggerFactory loggerFactory,
        IEnumerable<IInstallLinkingRollbackAuthorityReadinessProbe> rollbackAuthorities,
        DataProtectionKeyProtectionStatus? keyProtection = null,
        InstallLinkingPostgresAuthorityCoordinator? postgresAuthority = null)
    {
        _configuration = configuration;
        _dataProtectionProvider = dataProtectionProvider;
        _environment = environment;
        _loggerFactory = loggerFactory;
        _keyProtection = keyProtection ?? (environment.IsProduction()
            ? new DataProtectionKeyProtectionStatus(false, "data_protection_key_encryptor_status_missing")
            : new DataProtectionKeyProtectionStatus(true, "development_key_ring"));
        // Enumerate once so malformed custom registrations cannot defer side effects until a
        // readiness call. Production readiness below intentionally accepts only the integrated
        // coordinator that also owns store load and mutation CAS, never an arbitrary green probe.
        _ = rollbackAuthorities.ToArray();
        _postgresAuthority = postgresAuthority;
        _activation = new Lazy<ActivationResult>(Activate, LazyThreadSafetyMode.ExecutionAndPublication);
    }

    public InstallLinkingStore GetRequiredStore()
    {
        InstallLinkingStoreReadiness readiness = Evaluate();
        InstallLinkingStore? store = _activation.Value.Store;
        if (!readiness.Ready || store is null || !store.IsHealthy)
        {
            throw new InvalidOperationException("Install-linking durable store is unavailable.");
        }

        return store;
    }

    internal InstallLinkingStore GetActivatedStoreForDependencyInjection()
    {
        // Construct services from the one cached activation without claiming that the
        // external rollback boundary is ready. Public durable operations are admitted
        // separately through IInstallLinkingStoreReadinessProbe.
        InstallLinkingStore? store = _activation.Value.Store;
        if (store is null || !store.IsHealthy)
        {
            throw new InvalidOperationException("Install-linking durable store is unavailable.");
        }

        return store;
    }

    public InstallLinkingStoreReadiness Evaluate()
    {
        ActivationResult activation = _activation.Value;
        if (activation.Store is null)
        {
            return activation.Readiness;
        }

        if (!activation.Store.IsHealthy)
        {
            return new(false, "store_persistence_failed");
        }

        if (_environment.IsProduction())
        {
            InstallLinkingRollbackAuthorityReadiness authority = EvaluateRollbackAuthority();
            return new(authority.Ready, authority.Code);
        }

        return new(true, "store_activated");
    }

    private ActivationResult Activate()
    {
        if (_environment.IsProduction() && !LinuxSecureFile.IsSupportedPlatform)
        {
            return Failure("secure_file_platform_unsupported");
        }

        if (_environment.IsProduction()
            && string.IsNullOrWhiteSpace(
                _configuration["CHUMMER_INSTALL_LINKING_STORE_PATH"]
                ?? _configuration["InstallLinking:StorePath"]))
        {
            return Failure("store_path_not_explicit");
        }

        if (_environment.IsProduction() && !_keyProtection.Ready)
        {
            return Failure(_keyProtection.Code);
        }

        if (_environment.IsProduction() && _postgresAuthority is null)
        {
            return Failure("external_rollback_authority_unimplemented");
        }

        try
        {
            var store = new InstallLinkingStore(
                _configuration,
                _dataProtectionProvider,
                _loggerFactory.CreateLogger<InstallLinkingStore>(),
                _environment.IsProduction() ? _postgresAuthority : null);
            if (_environment.IsProduction())
            {
                // Generation + floor files protect against partial/local rollback only. They live
                // in the same failure domain as the snapshot, so they cannot prove that revoked
                // grants were not resurrected by a whole-volume rollback. No boolean/config
                // attestation is accepted as a substitute for an implemented external authority.
                return new ActivationResult(
                    store,
                    new InstallLinkingStoreReadiness(false, "external_rollback_authority_unverified"));
            }

            return new ActivationResult(store, new InstallLinkingStoreReadiness(true, "store_activated"));
        }
        catch
        {
            return Failure("store_activation_failed");
        }
    }

    private InstallLinkingRollbackAuthorityReadiness EvaluateRollbackAuthority()
    {
        if (_postgresAuthority is null)
        {
            return new(false, "external_rollback_authority_unimplemented");
        }

        try
        {
            return _postgresAuthority.Evaluate();
        }
        catch
        {
            return new(false, "external_rollback_authority_probe_failed");
        }
    }

    private static ActivationResult Failure(string code)
        => new(null, new InstallLinkingStoreReadiness(false, code));

    public void Dispose()
    {
        if (_activation.IsValueCreated)
        {
            _activation.Value.Store?.Dispose();
        }
    }

    private sealed record ActivationResult(
        InstallLinkingStore? Store,
        InstallLinkingStoreReadiness Readiness);
}
