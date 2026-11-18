using Chummer.Infrastructure.Workspaces;
using Microsoft.Extensions.Hosting;

using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.InstallLinking;

// A unit-test observation boundary, never resolved from DI or configuration.
// The host entry point below always selects the native implementation.
internal interface IPrivateRookFileSystemObservation
{
    void ValidatePrivateFile(string path);
    void ValidateSourceDirectory(string path);
}

/// <summary>
/// Explicit host-only composition, disabled by default. Registers no endpoint,
/// provider, hosted worker or authority substitute. Filesystem observations are
/// prerequisites, not approved-package evidence or proof of continuing custody.
/// The deployment owner must supply approved Core content on stable read-only
/// mounts and keep those mounts, configuration and private stores under custody.
/// </summary>
internal static class PrivateRookRuntimeConfiguration
{
    internal const string EnabledKey = "CHUMMER_ROOK_PRIVATE_RUNTIME_ENABLED";
    internal const string ScratchRootKey = "CHUMMER_ROOK_PRIVATE_SCRATCH_ROOT";
    internal const string BaseDirectoryKey = "CHUMMER_ROOK_PRIVATE_BASE_DIRECTORY";
    internal const string CurrentDirectoryKey = "CHUMMER_ROOK_PRIVATE_CURRENT_DIRECTORY";
    internal const string AmendsPathKey = "CHUMMER_ROOK_PRIVATE_AMENDS_PATH";
    private const string Unavailable = "Private Rook runtime configuration is unavailable.";

    internal static IServiceCollection AddHubPrivateRookRuntime(this IServiceCollection services,
        IConfiguration configuration, IHostEnvironment environment)
        => AddHubPrivateRookRuntime(services, configuration, environment, new NativeFileSystemObservation());

    // Deterministic composition tests can observe filesystem decisions without
    // privileged mount setup. This overload is not a deployment-admission API.
    internal static IServiceCollection AddHubPrivateRookRuntime(IServiceCollection services,
        IConfiguration configuration, IHostEnvironment environment, IPrivateRookFileSystemObservation observations)
    {
        if (!ReadFlag(configuration, EnabledKey)) return services;
        try
        {
            if (!environment.IsProduction() || ReadFlag(configuration, "CHUMMER_PUBLIC_DOWNLOAD_ONLY"))
                throw new InvalidOperationException();

            RequireIdentityOrigin(configuration["IDENTITY_SERVICE_BASE_URL"]);
            string scratch = RequirePath(configuration[ScratchRootKey]);
            string[] stores = [
                RequirePath(configuration["CHUMMER_COMMUNITY_STORE_PATH"]),
                RequirePath(configuration["CHUMMER_INSTALL_LINKING_STORE_PATH"]),
                RequirePath(configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"])];
            if (stores.Distinct(StringComparer.Ordinal).Count() != stores.Length)
                throw new InvalidOperationException();
            foreach (string store in stores)
            {
                if (Overlaps(scratch, Path.GetDirectoryName(store)!)) throw new InvalidOperationException();
                observations.ValidatePrivateFile(store);
            }

            // Program has already run the actual certificate/key-ring configurator.
            // A green arbitrary readiness probe is not used to admit store access.
            if (services.LastOrDefault(item => item.ServiceType == typeof(DataProtectionKeyProtectionStatus))
                    ?.ImplementationInstance is not DataProtectionKeyProtectionStatus { Ready: true })
                throw new InvalidOperationException();
            _ = RequirePath(configuration["CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH"]);
            _ = RequirePath(configuration["CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD_FILE"]);
            string keyRing = RequirePath(configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]);
            if (Overlaps(scratch, keyRing)) throw new InvalidOperationException();
            LinuxSecureFile.ValidateExistingDirectory(keyRing, ownerOnly: true, readOnlyFileSystem: false);

            string baseDirectory = RequirePath(configuration[BaseDirectoryKey]);
            string currentDirectory = RequirePath(configuration[CurrentDirectoryKey]);
            string? configuredAmends = configuration[AmendsPathKey];
            string[] amends = configuredAmends is null ? []
                : configuredAmends.Split([Path.PathSeparator, ';'], StringSplitOptions.TrimEntries)
                    .Select(RequirePath).ToArray();
            foreach (string source in new[] { baseDirectory, currentDirectory }.Concat(amends))
            {
                if (Overlaps(source, scratch)
                    || Overlaps(source, keyRing)
                    || stores.Any(store => Overlaps(source, Path.GetDirectoryName(store)!)))
                    throw new InvalidOperationException();
                observations.ValidateSourceDirectory(source);
            }
            RequireSourceSegment(baseDirectory, currentDirectory, "data", observations);
            RequireSourceSegment(baseDirectory, currentDirectory, "lang", observations);

            // Use Core's actual allocator validation; never construct a substitute
            // owner issuer, restore service or mutable user workspace store here.
            var factory = new PrivateWorkspaceRuleRuntimeFactory(scratch, baseDirectory,
                currentDirectory, configuredAmends is null ? null : string.Join(Path.PathSeparator, amends));
            services.AddSingleton(factory);
            services.AddTransient<RookWorkspaceRuleReadService>(provider =>
            {
                // Resolve through the integrated Production activation, including
                // its actual PostgreSQL coordinator, not a configurable green flag.
                _ = provider.GetRequiredService<InstallLinkingStoreActivation>().GetRequiredStore();
                return new RookWorkspaceRuleReadService(
                    provider.GetRequiredService<RookWorkspaceReadAdmissionService>(),
                    provider.GetRequiredService<PrivateWorkspaceRuleRuntimeFactory>());
            });
            return services;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException
            or InvalidOperationException or ArgumentException or NotSupportedException)
        {
            // No configured paths, credentials or underlying exception escape.
            throw new InvalidOperationException(Unavailable);
        }
    }

    private static bool ReadFlag(IConfiguration configuration, string key)
    {
        string? value = configuration[key];
        if (value is null) return false;
        if (value == "true") return true;
        if (value == "false") return false;
        throw new InvalidOperationException(Unavailable);
    }

    private static string RequirePath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path)
            || path.Any(char.IsControl) || path != path.Trim()
            || path != Path.GetFullPath(path) || path == Path.GetPathRoot(path)
            || path.EndsWith(Path.DirectorySeparatorChar))
            throw new InvalidOperationException();
        return path;
    }

    private static void RequireIdentityOrigin(string? value)
    {
        if (string.IsNullOrWhiteSpace(value) || value != value.Trim() || value.Any(char.IsControl)
            || !Uri.TryCreate(value, UriKind.Absolute, out Uri? origin)
            || origin.Scheme is not ("http" or "https") || origin.Host.Length == 0
            || origin.UserInfo.Length != 0 || origin.Query.Length != 0 || origin.Fragment.Length != 0
            || origin.AbsolutePath != "/")
            throw new InvalidOperationException();
    }

    private static bool Overlaps(string left, string right)
        => left == right || left.StartsWith(right + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            || right.StartsWith(left + Path.DirectorySeparatorChar, StringComparison.Ordinal);

    private static void RequireSourceSegment(string baseDirectory, string currentDirectory, string segment,
        IPrivateRookFileSystemObservation observations)
    {
        // Match the existing Core catalog's fallback order; do not replace active
        // base/current/custom-source selection with a hardcoded shared root.
        string? selected = new[] { Path.Combine(baseDirectory, segment),
            Path.Combine(baseDirectory, "Chummer", segment), Path.Combine(currentDirectory, segment),
            Path.Combine(currentDirectory, "Chummer", segment) }.FirstOrDefault(Directory.Exists);
        if (selected is null) throw new InvalidOperationException();
        observations.ValidateSourceDirectory(selected);
    }

    private sealed class NativeFileSystemObservation : IPrivateRookFileSystemObservation
    {
        public void ValidatePrivateFile(string path) => LinuxSecureFile.ValidateExistingPrivateFile(path);
        public void ValidateSourceDirectory(string path)
            => LinuxSecureFile.ValidateExistingDirectory(path, ownerOnly: false, readOnlyFileSystem: true);
    }
}
