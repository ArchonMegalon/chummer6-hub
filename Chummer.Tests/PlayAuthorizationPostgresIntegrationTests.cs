using System.Security.Cryptography;
using System.Reflection;
using System.Text;
using Chummer.Run.Api.Services.Community.Postgres;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Npgsql;
using NpgsqlTypes;
using Testcontainers.PostgreSql;
using Xunit;

namespace Chummer.Tests;

[Trait("Category", "PostgreSQLIntegration")]
public sealed class PlayAuthorizationPostgresIntegrationTests :
    IClassFixture<PlayAuthorizationPostgresFixture>
{
    private readonly PlayAuthorizationPostgresFixture _fixture;

    public PlayAuthorizationPostgresIntegrationTests(PlayAuthorizationPostgresFixture fixture)
    {
        _fixture = fixture;
    }

    [Fact]
    public async Task CheckpointProviderBoundaryAvoidsDirectRawRegistrationAndSealsTrustedComposition()
    {
        using var authority = new EphemeralTestAuthorities();
        var valid = new ServiceCollection();
        valid.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle activationHandle =
            valid.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);
        Assert.DoesNotContain(
            valid,
            DirectlyExposesCheckpointAuthority);
        using (ServiceProvider serviceProvider = activationHandle.BuildServiceProvider())
        {
            IHostedService startupValidation = Assert.Single(
                serviceProvider.GetServices<IHostedService>());
            await startupValidation.StartAsync(CancellationToken.None);
            PlayAuthorizationPostgresDormantFactory factory =
                serviceProvider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
            Assert.Same(
                factory,
                serviceProvider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
            Assert.Null(serviceProvider.GetService<IPlayAuthorizationCheckpointAuthority>());
            Assert.Null(serviceProvider.GetService<
                PlayAuthorizationCheckpointProviderActivation>());
        }

        Type[] factoryOnlyTypes =
        [
            typeof(NpgsqlPlayAuthorizationRepository),
            typeof(NpgsqlPlayAuthorizationCheckpointPublicationReconciler),
            typeof(PlayAuthorizationPostgresReadinessProbe),
            typeof(PlayAuthorizationCheckpointProviderActivation),
            typeof(PlayAuthorizationPostgresDormantFactory)
        ];
        foreach (Type type in factoryOnlyTypes)
        {
            ConstructorInfo[] constructors = type.GetConstructors(
                BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            Assert.NotEmpty(constructors);
            Assert.All(constructors, constructor => Assert.True(constructor.IsPrivate));
            Assert.DoesNotContain(
                type.GetMethods(BindingFlags.Public | BindingFlags.Static),
                method => string.Equals(method.Name, "Create", StringComparison.Ordinal));
        }

        Assert.Contains(
            typeof(PlayAuthorizationPostgresDormantFactory).GetMethods(),
            method => method.IsPublic
                && string.Equals(
                    method.Name,
                    nameof(PlayAuthorizationPostgresDormantFactory.CreateRepository),
                    StringComparison.Ordinal));
        MethodInfo[] publicFactoryApi = typeof(PlayAuthorizationPostgresDormantFactory)
            .GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly);
        Type[] forbiddenFactoryApiTypes =
        [
            typeof(IPlayAuthorizationCheckpointAuthority),
            typeof(IPlayAuthorizationCheckpointPublicationReconciler),
            typeof(NpgsqlPlayAuthorizationCheckpointPublicationReconciler),
            typeof(PlayAuthorizationCheckpointProviderActivation),
            typeof(object)
        ];
        Assert.DoesNotContain(publicFactoryApi, method =>
            forbiddenFactoryApiTypes.Contains(method.ReturnType)
            || method.GetParameters().Any(parameter =>
                forbiddenFactoryApiTypes.Contains(parameter.ParameterType)));
        Assert.DoesNotContain(publicFactoryApi, method =>
            string.Equals(method.Name, "CreateCheckpointReconciler", StringComparison.Ordinal));

        string programSource = File.ReadAllText(
            RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));
        Assert.DoesNotContain(
            nameof(PlayAuthorizationPostgresDormantProviderBoundary
                .AddPlayAuthorizationPostgresDormantProviderBoundary),
            programSource,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "new NpgsqlPlayAuthorizationRepository",
            programSource,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "new NpgsqlPlayAuthorizationCheckpointPublicationReconciler",
            programSource,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "new PlayAuthorizationPostgresReadinessProbe",
            programSource,
            StringComparison.Ordinal);

        AssertRejected(static _ => { });
        AssertRejected(static services =>
        {
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddSingleton<IPlayAuthorizationCheckpointAuthority, EphemeralTestAuthorities>();
        });
        AssertRejected(static services =>
        {
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddScoped<IPlayAuthorizationCheckpointAuthority, EphemeralTestAuthorities>();
        });
        AssertRejected(static services =>
        {
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddTransient<IPlayAuthorizationCheckpointAuthority, EphemeralTestAuthorities>();
        });
        AssertRejected(static services =>
        {
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddKeyedSingleton<
                IPlayAuthorizationCheckpointAuthority,
                EphemeralTestAuthorities>("alias");
        });
        AssertRejected(static services =>
        {
            services.AddSingleton<EphemeralTestAuthorities>();
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        });
        AssertRejected(static services =>
        {
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddSingleton(
                typeof(OpenGenericCheckpointAuthority<>),
                typeof(OpenGenericCheckpointAuthority<>));
        });
        AssertRejected(static services =>
        {
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        });
        AssertRejected(static services =>
        {
            services.AddScoped<PlayAuthorizationCheckpointProviderCallRegistry>();
        });
        AssertRejected(static services =>
        {
            services.AddTransient<PlayAuthorizationCheckpointProviderCallRegistry>();
        });

        using (var aliasedInstance = new EphemeralTestAuthorities())
        {
            AssertRejected(services =>
            {
                services.AddSingleton<object>(aliasedInstance);
                services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            });
        }

        var duplicate = new ServiceCollection();
        duplicate.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        duplicate.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);
        Assert.Throws<InvalidOperationException>(() =>
            duplicate.AddPlayAuthorizationPostgresDormantProviderBoundary(authority));

        static bool DirectlyExposesCheckpointAuthority(ServiceDescriptor descriptor)
        {
            Type? implementationType = descriptor.IsKeyedService
                ? descriptor.KeyedImplementationType
                : descriptor.ImplementationType;
            object? instance = descriptor.IsKeyedService
                ? descriptor.KeyedImplementationInstance
                : descriptor.ImplementationInstance;
            return typeof(IPlayAuthorizationCheckpointAuthority)
                       .IsAssignableFrom(descriptor.ServiceType)
                   || (implementationType is not null
                       && (typeof(IPlayAuthorizationCheckpointAuthority)
                               .IsAssignableFrom(implementationType)
                           || implementationType.GetInterfaces().Contains(
                               typeof(IPlayAuthorizationCheckpointAuthority))))
                   || instance is IPlayAuthorizationCheckpointAuthority;
        }

        static void AssertRejected(Action<IServiceCollection> configure)
        {
            using var boundaryAuthority = new EphemeralTestAuthorities();
            var services = new ServiceCollection();
            configure(services);
            Assert.Throws<InvalidOperationException>(() =>
                services.AddPlayAuthorizationPostgresDormantProviderBoundary(
                    boundaryAuthority));
        }
    }

    [Fact]
    public async Task CheckpointAuthorityAliasSurfacesCannotResolveBoundaryAuthority()
    {
        using var authority = new EphemeralTestAuthorities();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        services.AddSingleton<object>(serviceProvider =>
            serviceProvider.GetRequiredService<IPlayAuthorizationCheckpointAuthority>());
        services.AddKeyedSingleton<object>("checkpoint", (serviceProvider, _) =>
            serviceProvider.GetRequiredService<IPlayAuthorizationCheckpointAuthority>());
        services.AddSingleton<Func<IPlayAuthorizationCheckpointAuthority>>(serviceProvider =>
            () => serviceProvider.GetRequiredService<
                IPlayAuthorizationCheckpointAuthority>());
        services.AddSingleton<Lazy<IPlayAuthorizationCheckpointAuthority>>(serviceProvider =>
            new Lazy<IPlayAuthorizationCheckpointAuthority>(() =>
                serviceProvider.GetRequiredService<
                    IPlayAuthorizationCheckpointAuthority>()));
        services.AddSingleton<CheckpointAuthorityPropertyWrapper>(serviceProvider =>
            new CheckpointAuthorityPropertyWrapper(
                serviceProvider.GetRequiredService<
                    IPlayAuthorizationCheckpointAuthority>()));
        PlayAuthorizationPostgresDormantProviderActivationHandle activationHandle =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);

        using ServiceProvider serviceProvider = activationHandle.BuildServiceProvider();
        IHostedService startup = Assert.Single(
            serviceProvider.GetServices<IHostedService>());
        await startup.StartAsync(CancellationToken.None);
        Assert.NotNull(serviceProvider.GetRequiredService<
            PlayAuthorizationPostgresDormantFactory>());
        Assert.Null(serviceProvider.GetService<IPlayAuthorizationCheckpointAuthority>());
        Assert.Throws<InvalidOperationException>(() =>
            serviceProvider.GetRequiredService<object>());
        Assert.Throws<InvalidOperationException>(() =>
            serviceProvider.GetRequiredKeyedService<object>("checkpoint"));
        Func<IPlayAuthorizationCheckpointAuthority> factory =
            serviceProvider.GetRequiredService<
                Func<IPlayAuthorizationCheckpointAuthority>>();
        Assert.Throws<InvalidOperationException>(() => factory());
        Lazy<IPlayAuthorizationCheckpointAuthority> lazy =
            serviceProvider.GetRequiredService<
                Lazy<IPlayAuthorizationCheckpointAuthority>>();
        Assert.Throws<InvalidOperationException>(() => _ = lazy.Value);
        Assert.Throws<InvalidOperationException>(() =>
            serviceProvider.GetRequiredService<
                CheckpointAuthorityPropertyWrapper>());
    }

    [Fact]
    public async Task BoundaryDescriptorsRejectReplacementReuseAndLateMutation()
    {
        using var authorityA = new EphemeralTestAuthorities();
        var original = new ServiceCollection();
        original.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle originalActivation =
            original.AddPlayAuthorizationPostgresDormantProviderBoundary(authorityA);
        ServiceDescriptor[] originalDescriptors = original.ToArray();
        using ServiceProvider originalProvider = originalActivation.BuildServiceProvider();
        IHostedService originalStartup = Assert.Single(
            originalProvider.GetServices<IHostedService>());
        await originalStartup.StartAsync(CancellationToken.None);
        PlayAuthorizationPostgresDormantFactory originalFactory =
            originalProvider.GetRequiredService<
                PlayAuthorizationPostgresDormantFactory>();

        var copied = new ServiceCollection();
        foreach (ServiceDescriptor descriptor in originalDescriptors)
        {
            ((ICollection<ServiceDescriptor>)copied).Add(descriptor);
        }

        using (ServiceProvider copiedProvider = copied.BuildServiceProvider())
        {
            Assert.Throws<InvalidOperationException>(() =>
                copiedProvider.GetRequiredService<
                    PlayAuthorizationPostgresDormantFactory>());
        }

        using var authorityB = new EphemeralTestAuthorities();
        var replaced = new ServiceCollection();
        replaced.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle replacedActivation =
            replaced.AddPlayAuthorizationPostgresDormantProviderBoundary(authorityB);
        ServiceDescriptor replacedFactory = Assert.Single(
            replaced,
            descriptor => descriptor.ServiceType
                == typeof(PlayAuthorizationPostgresDormantFactory));
        Assert.True(replaced.Remove(replacedFactory));
        replaced.AddSingleton(originalFactory);
        Assert.Throws<InvalidOperationException>(() =>
            replacedActivation.BuildServiceProvider());

        AssertLateMutationRejected(services =>
            services.AddSingleton<object>(serviceProvider =>
                serviceProvider.GetRequiredService<
                    IPlayAuthorizationCheckpointAuthority>()));
        AssertLateMutationRejected(services =>
            services.AddKeyedSingleton<object>("checkpoint", (serviceProvider, _) =>
                serviceProvider.GetRequiredService<
                    IPlayAuthorizationCheckpointAuthority>()));
        AssertLateMutationRejected(services =>
            services.AddSingleton<Func<IPlayAuthorizationCheckpointAuthority>>(
                serviceProvider => () => serviceProvider.GetRequiredService<
                    IPlayAuthorizationCheckpointAuthority>()));
        AssertLateMutationRejected(services =>
            services.AddSingleton<Lazy<IPlayAuthorizationCheckpointAuthority>>(
                serviceProvider => new Lazy<IPlayAuthorizationCheckpointAuthority>(
                    () => serviceProvider.GetRequiredService<
                        IPlayAuthorizationCheckpointAuthority>())));
        AssertLateMutationRejected(services =>
            services.AddSingleton<CheckpointAuthorityPropertyWrapper>(
                serviceProvider => new CheckpointAuthorityPropertyWrapper(
                    serviceProvider.GetRequiredService<
                        IPlayAuthorizationCheckpointAuthority>())));

        static void AssertLateMutationRejected(
            Action<IServiceCollection> mutate)
        {
            using var authority = new EphemeralTestAuthorities();
            var services = new ServiceCollection();
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            PlayAuthorizationPostgresDormantProviderActivationHandle activation =
                services.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);
            mutate(services);
            Assert.Throws<InvalidOperationException>(() =>
                activation.BuildServiceProvider());
        }
    }

    [Fact]
    public async Task ClosureOwnedCheckpointAuthorityPreservesIdentityAndDisposalOwnership()
    {
        var syncAuthority = new DisposalTrackingCheckpointAuthority(_fixture.Authorities);
        int syncFactoryCalls = 0;
        using (ServiceProvider syncProvider = BuildProvider(services =>
               services.AddPlayAuthorizationPostgresDormantProviderBoundary(_ =>
               {
                   Interlocked.Increment(ref syncFactoryCalls);
                   return syncAuthority;
               })))
        {
            PlayAuthorizationPostgresDormantFactory factory =
                syncProvider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
            Assert.Same(
                factory,
                syncProvider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
            Assert.Same(
                syncAuthority,
                ReadPrivate(ReadPrivate(factory, "_provider"), "_authority"));
            Assert.Null(syncProvider.GetService<IPlayAuthorizationCheckpointAuthority>());
            Assert.Equal(1, syncFactoryCalls);

            syncProvider.Dispose();
            syncProvider.Dispose();
            Assert.Equal(1, syncAuthority.DisposeCount);
            Assert.Equal(0, syncAuthority.DisposeAsyncCount);
        }

        var asyncAuthority = new DisposalTrackingCheckpointAuthority(_fixture.Authorities);
        ServiceProvider asyncProvider = BuildProvider(services =>
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(
                _ => asyncAuthority));
        _ = asyncProvider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
        await asyncProvider.DisposeAsync();
        await asyncProvider.DisposeAsync();
        Assert.Equal(0, asyncAuthority.DisposeCount);
        Assert.Equal(1, asyncAuthority.DisposeAsyncCount);

        var externalAuthority = new DisposalTrackingCheckpointAuthority(_fixture.Authorities);
        using (ServiceProvider externalProvider = BuildProvider(services =>
               services.AddPlayAuthorizationPostgresDormantProviderBoundary(
                   externalAuthority)))
        {
            _ = externalProvider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
            externalProvider.Dispose();
            Assert.Equal(0, externalAuthority.DisposeCount);
            Assert.Equal(0, externalAuthority.DisposeAsyncCount);
        }

        externalAuthority.Dispose();
        Assert.Equal(1, externalAuthority.DisposeCount);

        static ServiceProvider BuildProvider(
            Func<IServiceCollection,
                PlayAuthorizationPostgresDormantProviderActivationHandle> configure)
        {
            var services = new ServiceCollection();
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            PlayAuthorizationPostgresDormantProviderActivationHandle activation =
                configure(services);
            return activation.BuildServiceProvider();
        }
    }

    [Fact]
    public void DormantFactoryLeaseRejectsProviderMixingAndOwnsAllConstructedObjects()
    {
        PlayAuthorizationPostgresDormantFactory factoryA =
            _fixture.CreateProviderFactory(_fixture.Authorities)
                .BindCheckpointReconciliation(
                    _fixture.AdminDataSource,
                    _fixture.Authorities,
                    _fixture.PublicationPolicy,
                    TimeProvider.System);
        var providerB = new AliasingCheckpointAuthority(_fixture.Authorities);
        PlayAuthorizationPostgresDormantFactory factoryB =
            _fixture.CreateProviderFactory(providerB)
                .BindCheckpointReconciliation(
                    _fixture.AdminDataSource,
                    _fixture.Authorities,
                    _fixture.PublicationPolicy,
                    TimeProvider.System);
        NpgsqlPlayAuthorizationRepository repository = Assert.IsType<
            NpgsqlPlayAuthorizationRepository>(_fixture.CreateRepository(
                _fixture.AdminDataSource,
                providerFactory: factoryA));
        PlayAuthorizationPostgresReadinessProbe readiness = factoryA.CreateReadinessProbe(
            _fixture.AdminDataSource,
            new PlayAuthorizationPostgresMigrator(_fixture.AdminDataSource),
            _fixture.Authorities,
            _fixture.PublicationPolicy,
            _fixture.ReplaySafetyPolicy,
            TimeProvider.System);

        object activationA = ReadPrivate(factoryA, "_provider");
        object activationB = ReadPrivate(factoryB, "_provider");
        object leaseA = ReadPrivate(factoryA, "_constructionLease");
        object reconcilerA = ReadPrivate(factoryA, "_reconciler");
        object reconcilerB = ReadPrivate(factoryB, "_reconciler");
        Assert.NotSame(activationA, activationB);
        Assert.Same(activationA, ReadPrivate(reconcilerA, "_checkpointProvider"));
        Assert.Same(activationA, ReadPrivate(repository, "_checkpointProvider"));
        Assert.Same(reconcilerA, ReadPrivate(repository, "_checkpointReconciler"));
        Assert.Same(activationA, ReadPrivate(readiness, "_checkpointProvider"));
        Assert.Same(reconcilerA, ReadPrivate(readiness, "_checkpointReconciler"));

        Type[] factoryLeaseProtectedTypes =
        [
            typeof(PlayAuthorizationCheckpointProviderActivation),
            typeof(PlayAuthorizationPostgresDormantFactory),
            typeof(NpgsqlPlayAuthorizationCheckpointPublicationReconciler),
            typeof(NpgsqlPlayAuthorizationRepository),
            typeof(PlayAuthorizationPostgresReadinessProbe)
        ];
        foreach (Type type in factoryLeaseProtectedTypes)
        {
            MethodInfo create = Assert.Single(
                type.GetMethods(BindingFlags.Static | BindingFlags.NonPublic),
                method => string.Equals(method.Name, "Create", StringComparison.Ordinal));
            object?[] arguments = new object?[create.GetParameters().Length];
            arguments[0] = new object();
            if (arguments.Length > 1
                && create.GetParameters()[1].ParameterType
                    == typeof(PlayAuthorizationCheckpointProviderActivation))
            {
                arguments[1] = activationA;
            }

            TargetInvocationException forgedLease =
                Assert.Throws<TargetInvocationException>(() =>
                {
                    _ = create.Invoke(null, arguments);
                });
            Assert.IsType<InvalidOperationException>(forgedLease.InnerException);
        }

        MethodInfo createReconciler = Assert.Single(
            typeof(NpgsqlPlayAuthorizationCheckpointPublicationReconciler)
                .GetMethods(BindingFlags.Static | BindingFlags.NonPublic),
            method => string.Equals(method.Name, "Create", StringComparison.Ordinal));
        AssertLeaseRejected(leaseA, activationB);
        AssertLeaseRejected(new object(), activationA);

        MethodInfo createRepository = Assert.Single(
            typeof(NpgsqlPlayAuthorizationRepository)
                .GetMethods(BindingFlags.Static | BindingFlags.NonPublic),
            method => string.Equals(method.Name, "Create", StringComparison.Ordinal));
        TargetInvocationException reconcilerMismatch =
            Assert.Throws<TargetInvocationException>(() =>
            {
                _ = createRepository.Invoke(
                    null,
                    [
                        leaseA,
                        activationA,
                        null,
                        null,
                        null,
                        null,
                        reconcilerB,
                        null,
                        null,
                        null
                    ]);
            });
        Assert.IsType<InvalidOperationException>(reconcilerMismatch.InnerException);

        void AssertLeaseRejected(object lease, object activation)
        {
            TargetInvocationException exception = Assert.Throws<TargetInvocationException>(() =>
            {
                _ = createReconciler.Invoke(
                    null,
                    [
                        lease,
                        activation,
                        _fixture.AdminDataSource,
                        _fixture.Authorities,
                        _fixture.PublicationPolicy,
                        TimeProvider.System
                    ]);
            });
            Assert.IsType<InvalidOperationException>(exception.InnerException);
        }

        static object ReadPrivate(object target, string fieldName)
            => target.GetType()
                   .GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic)
                   ?.GetValue(target)
               ?? throw new InvalidOperationException($"Missing private field {fieldName}.");
    }

    [Fact]
    public async Task MigrationsReadinessAndLeastPrivilegeContractAreRealPostgresValidated()
    {
        var migrator = new PlayAuthorizationPostgresMigrator(_fixture.AdminDataSource);
        PlayAuthorizationPostgresSchemaValidation schema = await migrator.ValidateAsync();
        Assert.True(schema.Valid, string.Join(',', schema.Problems));
        Assert.Equal(PlayAuthorizationPostgresSchema.CurrentVersion, schema.AppliedVersion);

        PlayAuthorizationPostgresDormantFactory providerFactory =
            _fixture.CreateProviderFactory(_fixture.Authorities);
        PlayAuthorizationPostgresReadinessProbe readiness = providerFactory.CreateReadinessProbe(
            _fixture.AdminDataSource,
            migrator,
            _fixture.Authorities,
            _fixture.PublicationPolicy,
            _fixture.ReplaySafetyPolicy,
            TimeProvider.System);
        PlayAuthorizationPostgresReadiness ready = await readiness.CheckAsync();
        Assert.True(ready.Ready, ready.Code);
        Assert.Equal(0, providerFactory.ProviderCallDiagnostics.TotalCallsInFlight);

        var unavailable = new UnavailablePlayAuthorizationExternalAuthorities();
        Assert.Throws<InvalidOperationException>(() =>
            _fixture.CreateProviderFactory(unavailable));
        var invalidHmacContract = new CheckpointCapabilityOverrideAuthority(
            _fixture.Authorities,
            _fixture.Authorities.Capabilities with { HmacSizeInBytes = 64 });
        Assert.Throws<InvalidOperationException>(() =>
            _fixture.CreateProviderFactory(invalidHmacContract));

        string runtimeRole = $"play_runtime_{Guid.NewGuid():N}";
        string runtimePassword = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        bool roleCreated = false;
        SeededInvite? seed = null;
        byte[]? exchangeSecret = null;
        byte[]? body = null;
        try
        {
            await using (NpgsqlConnection connection =
                         await _fixture.AdminDataSource.OpenConnectionAsync())
            await using (NpgsqlCommand createRole = connection.CreateCommand())
            {
                createRole.CommandText =
                    $"CREATE ROLE \"{runtimeRole}\" LOGIN PASSWORD '{runtimePassword}'";
                await createRole.ExecuteNonQueryAsync();
                roleCreated = true;
            }

            await migrator.GrantRuntimePrivilegesAsync(runtimeRole);
            Assert.True(await migrator.ValidateRuntimePrivilegesAsync(runtimeRole));

            seed = await _fixture.SeedInviteAsync();
            exchangeSecret = RandomNumberGenerator.GetBytes(48);
            body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
            var runtimeConnection = new NpgsqlConnectionStringBuilder(_fixture.ConnectionString)
            {
                Username = runtimeRole,
                Password = runtimePassword,
                Pooling = false
            };
            await using (NpgsqlDataSource runtimeDataSource =
                         NpgsqlDataSource.Create(runtimeConnection.ConnectionString))
            {
                IPlayAuthorizationPostgresRepository runtimeRepository =
                    _fixture.CreateRepository(runtimeDataSource);
                PlayAuthorizationPostgresMutationResult permitted =
                    await runtimeRepository.RedeemInviteAsync(seed.Redeem(
                        Durable(
                            "runtime-role-redeem",
                            "runtime-role-key",
                            "runtime-role-body",
                            body),
                        exchangeSecret));
                Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Applied, permitted.Code);

                await using NpgsqlConnection runtimeConnectionHandle =
                    await runtimeDataSource.OpenConnectionAsync();
                await using NpgsqlCommand forbidden = runtimeConnectionHandle.CreateCommand();
                forbidden.CommandText =
                    "DELETE FROM play_auth.sessions WHERE session_id = @session";
                forbidden.Parameters.AddWithValue("session", seed.SessionId);
                PostgresException denied = await Assert.ThrowsAsync<PostgresException>(
                    () => forbidden.ExecuteNonQueryAsync());
                Assert.Equal(PostgresErrorCodes.InsufficientPrivilege, denied.SqlState);
            }

            Assert.Equal(1, await _fixture.CountAsync(
                "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
                seed.ExchangeId));
        }
        finally
        {
            if (exchangeSecret is not null)
            {
                CryptographicOperations.ZeroMemory(exchangeSecret);
            }

            if (body is not null)
            {
                CryptographicOperations.ZeroMemory(body);
            }

            if (seed is not null)
            {
                CryptographicOperations.ZeroMemory(seed.InviteSecret);
            }

            if (roleCreated)
            {
                await using NpgsqlConnection connection =
                    await _fixture.AdminDataSource.OpenConnectionAsync();
                await using NpgsqlCommand dropRole = connection.CreateCommand();
                dropRole.CommandText = $"""
                    DROP OWNED BY "{runtimeRole}";
                    DROP ROLE IF EXISTS "{runtimeRole}";
                    """;
                await dropRole.ExecuteNonQueryAsync();
            }
        }
    }

    [Fact]
    public async Task ThirtyTwoIndependentDataSourcesRedeemExactlyOnceAndReplayByteIdentically()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes(
            $"{{\"exchangeId\":\"{seed.ExchangeId}\",\"secret\":\"{Convert.ToBase64String(exchangeSecret)}\"}}");
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(
            Durable("concurrent-redeem", "shared-idempotency-key", "concurrent-body", body),
            exchangeSecret);

        var dataSources = Enumerable.Range(0, 32)
            .Select(_ => NpgsqlDataSource.Create(_fixture.ConnectionString))
            .ToArray();
        try
        {
            Task<PlayAuthorizationPostgresMutationResult>[] attempts = dataSources
                .Select(dataSource => _fixture.CreateRepository(dataSource).RedeemInviteAsync(mutation))
                .ToArray();
            PlayAuthorizationPostgresMutationResult[] results = await Task.WhenAll(attempts);

            Assert.Single(results, result => result.Code == PlayAuthorizationPostgresOutcomeCode.Applied);
            Assert.Equal(31, results.Count(result => result.Code == PlayAuthorizationPostgresOutcomeCode.Replayed));
            Assert.All(results, result => Assert.Equal(body, result.Response?.Body));
            Assert.Equal(1, await _fixture.CountAsync(
                "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
                seed.ExchangeId));
            Assert.Equal(1, await _fixture.CountAsync(
                "SELECT COUNT(*) FROM play_auth.audit_log WHERE operation = 'redeem_invite' AND aggregate_id = @id",
                seed.InviteId));
        }
        finally
        {
            foreach (NpgsqlDataSource dataSource in dataSources)
            {
                await dataSource.DisposeAsync();
            }

            CryptographicOperations.ZeroMemory(exchangeSecret);
            CryptographicOperations.ZeroMemory(body);
        }
    }

    [Fact]
    public async Task CommitAmbiguityRestartConflictAndCiphertextAreFailClosedAndSecretFree()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        string encodedSecret = Convert.ToBase64String(exchangeSecret);
        byte[] responseBody = Encoding.UTF8.GetBytes(
            $"{{\"exchangeId\":\"{seed.ExchangeId}\",\"secret\":\"{encodedSecret}\"}}");
        PlayAuthorizationDurableRequest durable = Durable(
            "ambiguous-redeem",
            "ambiguous-key-0001",
            "ambiguous-body",
            responseBody);
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(durable, exchangeSecret);

        CommitThenThrowOnceUnitOfWorkFactory ambiguousCommit;
        await using (NpgsqlDataSource firstDataSource = NpgsqlDataSource.Create(_fixture.ConnectionString))
        {
            ambiguousCommit = new CommitThenThrowOnceUnitOfWorkFactory(
                new NpgsqlPlayAuthorizationUnitOfWorkFactory(firstDataSource));
            IPlayAuthorizationPostgresRepository first = _fixture.CreateRepository(
                firstDataSource,
                unitOfWorkFactory: ambiguousCommit);
            PlayAuthorizationPostgresMutationResult ambiguous = await first.RedeemInviteAsync(mutation);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Replayed, ambiguous.Code);
            Assert.Equal(responseBody, ambiguous.Response?.Body);
        }

        IDataProtectionProvider restartedProtection = DataProtectionProvider.Create(
            new DirectoryInfo(_fixture.DataProtectionPath),
            configuration => configuration.SetApplicationName("Chummer.PlayAuthorization.Postgres.Tests"));
        await using (NpgsqlDataSource restartedDataSource = NpgsqlDataSource.Create(_fixture.ConnectionString))
        {
            IPlayAuthorizationPostgresRepository restarted = _fixture.CreateRepository(
                restartedDataSource,
                receiptCipher: new DataProtectionPlayAuthorizationReceiptCipher(restartedProtection));
            PlayAuthorizationPostgresMutationResult replay = await restarted.RedeemInviteAsync(mutation);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Replayed, replay.Code);
            Assert.Equal(responseBody, replay.Response?.Body);

            PlayAuthorizationRedeemMutation conflicting = mutation with
            {
                DurableRequest = durable with { FingerprintSha256 = Sha256("different-request") }
            };
            PlayAuthorizationPostgresMutationResult conflict = await restarted.RedeemInviteAsync(conflicting);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.FingerprintConflict, conflict.Code);
        }

        await using NpgsqlConnection connection = await _fixture.AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT response_ciphertext,
                   (SELECT COUNT(*)
                    FROM play_auth.idempotency_receipts AS counted
                    WHERE counted.scope_sha256 = @scope AND counted.key_sha256 = @key)
            FROM play_auth.idempotency_receipts AS receipt
            WHERE receipt.scope_sha256 = @scope AND receipt.key_sha256 = @key
            """;
        command.Parameters.AddWithValue("scope", NpgsqlDbType.Bytea, SHA256.HashData(Encoding.UTF8.GetBytes(durable.Scope)));
        command.Parameters.AddWithValue("key", NpgsqlDbType.Bytea, SHA256.HashData(Encoding.UTF8.GetBytes(durable.IdempotencyKey)));
        await using NpgsqlDataReader receipt = await command.ExecuteReaderAsync();
        Assert.True(await receipt.ReadAsync());
        byte[] ciphertext = ((byte[])receipt[0]).ToArray();
        Assert.Equal(1L, receipt.GetInt64(1));
        await receipt.DisposeAsync();
        Assert.False(Contains(ciphertext, responseBody));
        Assert.False(Contains(ciphertext, Encoding.UTF8.GetBytes(encodedSecret)));
        Assert.DoesNotContain(encodedSecret, ambiguousCommit.FailureMessage, StringComparison.Ordinal);
        Assert.Equal(1, ambiguousCommit.BeginCount);
        Assert.Equal(1, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.audit_log WHERE aggregate_id = @id",
            seed.InviteId));
        Assert.Equal(1, await _fixture.CountAsync(
            """
            SELECT COUNT(*)
            FROM play_auth.checkpoint_publications AS publication
            JOIN play_auth.audit_log AS audit ON audit.sequence = publication.audit_sequence
            WHERE audit.aggregate_id = @id
            """,
            seed.InviteId));

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(responseBody);
        CryptographicOperations.ZeroMemory(ciphertext);
    }

    [Fact]
    public async Task AuditAuthorityFailureRollsBackThenSameIdempotencyKeyCanRetry()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(
            Durable("rollback-redeem", "rollback-key-0001", "rollback-body", body),
            exchangeSecret);

        var failingAuthority = new FailAuditOnceAuthority(_fixture.Authorities);
        await using NpgsqlDataSource failingDataSource = NpgsqlDataSource.Create(_fixture.ConnectionString);
        IPlayAuthorizationPostgresRepository failing = _fixture.CreateRepository(
            failingDataSource,
            hmacAuthority: failingAuthority);
        PlayAuthorizationPostgresMutationResult failed = await failing.RedeemInviteAsync(mutation);
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable, failed.Code);
        Assert.Equal(0, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
            seed.ExchangeId));

        IPlayAuthorizationPostgresRepository retry = _fixture.CreateRepository(_fixture.AdminDataSource);
        PlayAuthorizationPostgresMutationResult succeeded = await retry.RedeemInviteAsync(mutation);
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Applied, succeeded.Code);
        Assert.Equal(1, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
            seed.ExchangeId));

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task SixtyFourByteCapabilityOrAuditHmacIsRejectedBeforeTransaction(
        bool malformedAudit)
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        string malformedStage = malformedAudit ? "audit" : "capability";
        PlayAuthorizationDurableRequest durable = Durable(
            $"hmac-size-{malformedStage}",
            $"hmac-size-key-{malformedStage}",
            $"hmac-size-body-{malformedStage}",
            body);
        var unitOfWorkFactory = new CountingUnitOfWorkFactory(
            new NpgsqlPlayAuthorizationUnitOfWorkFactory(_fixture.AdminDataSource));
        var malformed = new SixtyFourByteHmacAuthority(_fixture.Authorities, malformedAudit);
        IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
            _fixture.AdminDataSource,
            hmacAuthority: malformed,
            unitOfWorkFactory: unitOfWorkFactory);

        PlayAuthorizationPostgresMutationResult result = await repository.RedeemInviteAsync(
            seed.Redeem(durable, exchangeSecret));

        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.PersistenceUnavailable, result.Code);
        Assert.Equal(0, unitOfWorkFactory.BeginCount);
        Assert.Equal(0, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
            seed.ExchangeId));
        Assert.Equal(0, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.audit_log WHERE aggregate_id = @id",
            seed.InviteId));
        await using (NpgsqlConnection connection =
                     await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand receipt = connection.CreateCommand())
        {
            receipt.CommandText = """
                SELECT COUNT(*) FROM play_auth.idempotency_receipts
                WHERE scope_sha256 = @scope AND key_sha256 = @key
                """;
            receipt.Parameters.AddWithValue(
                "scope",
                NpgsqlDbType.Bytea,
                SHA256.HashData(Encoding.UTF8.GetBytes(durable.Scope)));
            receipt.Parameters.AddWithValue(
                "key",
                NpgsqlDbType.Bytea,
                SHA256.HashData(Encoding.UTF8.GetBytes(durable.IdempotencyKey)));
            Assert.Equal(0L, Convert.ToInt64(await receipt.ExecuteScalarAsync()));
        }

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    [Fact]
    public async Task LifecycleConstraintsAndOneTimeTransitionsRejectMalformedOrRepeatedUse()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        await using NpgsqlConnection connection = await _fixture.AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand malformed = connection.CreateCommand();
        malformed.CommandText = """
            INSERT INTO play_auth.participants(
                participant_id, session_id, user_id, role, source_kind, source_id,
                status, authorization_version, epoch, generation, added_by_user_id,
                created_at_utc, updated_at_utc)
            VALUES (@id, @session, 'malformed-user', 'owner', 'explicit_participant', 'bad',
                'active', 1, 1, 1, 'admin', clock_timestamp(), clock_timestamp())
            """;
        malformed.Parameters.AddWithValue("id", $"malformed-{Guid.NewGuid():N}");
        malformed.Parameters.AddWithValue("session", seed.SessionId);
        PostgresException invalidRole = await Assert.ThrowsAsync<PostgresException>(
            () => malformed.ExecuteNonQueryAsync());
        Assert.Equal(PostgresErrorCodes.CheckViolation, invalidRole.SqlState);
        Assert.DoesNotContain(Convert.ToBase64String(seed.InviteSecret), invalidRole.ToString(), StringComparison.Ordinal);

        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(
            Durable("one-time-redeem", "one-time-key-0001", "one-time-body", body),
            exchangeSecret);
        IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(_fixture.AdminDataSource);
        PlayAuthorizationRedeemMutation caseVariant = mutation with
        {
            DurableRequest = Durable(
                "case-sensitive-redeem",
                "case-sensitive-key",
                "case-sensitive-body",
                body),
            UserId = mutation.UserId.ToUpperInvariant()
        };
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.VersionMismatch,
            (await repository.RedeemInviteAsync(caseVariant)).Code);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await repository.RedeemInviteAsync(mutation)).Code);

        PlayAuthorizationRedeemMutation repeated = mutation with
        {
            DurableRequest = Durable("one-time-redeem", "one-time-key-0002", "one-time-body", body),
            ExchangeId = $"exchange-{Guid.NewGuid():N}"
        };
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.AlreadyConsumed,
            (await repository.RedeemInviteAsync(repeated)).Code);

        Assert.Equal(1, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.exchanges WHERE invite_id = @id",
            seed.InviteId));

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    [Fact]
    public async Task PublishFailureLeavesPendingOutboxAndRestartReconcilesBeforeReplay()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(
            Durable("publish-recovery", "publish-recovery-key", "publish-recovery-body", body),
            exchangeSecret);

        var unavailablePublisher = new AlwaysUnavailableCheckpointPublisher(_fixture.Authorities);
        await using (NpgsqlDataSource firstDataSource = NpgsqlDataSource.Create(_fixture.ConnectionString))
        {
            IPlayAuthorizationPostgresRepository first = _fixture.CreateRepository(
                firstDataSource,
                checkpointAuthority: unavailablePublisher);
            PlayAuthorizationPostgresMutationResult pending = await first.RedeemInviteAsync(mutation);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.CheckpointPending, pending.Code);
        }

        Assert.Equal(1, await _fixture.CountAsync(
            """
            SELECT COUNT(*)
            FROM play_auth.checkpoint_publications AS publication
            JOIN play_auth.audit_log AS audit ON audit.sequence = publication.audit_sequence
            WHERE audit.aggregate_id = @id AND publication.state = 'pending'
            """,
            seed.InviteId));

        SeededInvite blockedSeed = await _fixture.SeedInviteAsync();
        byte[] blockedSecret = RandomNumberGenerator.GetBytes(48);
        byte[] blockedBody = Encoding.UTF8.GetBytes(
            $"{{\"exchangeId\":\"{blockedSeed.ExchangeId}\"}}");
        PlayAuthorizationPostgresMutationResult blocked = await _fixture.CreateRepository(
                _fixture.AdminDataSource,
                checkpointAuthority: unavailablePublisher)
            .RedeemInviteAsync(blockedSeed.Redeem(
                Durable("pending-race", "pending-race-key", "pending-race-body", blockedBody),
                blockedSecret));
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.CheckpointPending, blocked.Code);
        Assert.Equal(0, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
            blockedSeed.ExchangeId));
        Assert.Equal(0, await _fixture.CountAsync(
            "SELECT COUNT(*) FROM play_auth.audit_log WHERE aggregate_id = @id",
            blockedSeed.InviteId));

        await using (NpgsqlDataSource restartedDataSource = NpgsqlDataSource.Create(_fixture.ConnectionString))
        {
            IPlayAuthorizationPostgresRepository restarted =
                _fixture.CreateRepository(restartedDataSource);
            PlayAuthorizationPostgresMutationResult replay = await restarted.RedeemInviteAsync(mutation);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Replayed, replay.Code);
            Assert.Equal(body, replay.Response?.Body);
        }

        Assert.Equal(1, await _fixture.CountAsync(
            """
            SELECT COUNT(*)
            FROM play_auth.checkpoint_publications AS publication
            JOIN play_auth.audit_log AS audit ON audit.sequence = publication.audit_sequence
            WHERE audit.aggregate_id = @id AND publication.state = 'published'
            """,
            seed.InviteId));

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(blockedSecret);
        CryptographicOperations.ZeroMemory(body);
        CryptographicOperations.ZeroMemory(blockedBody);
    }

    [Fact]
    public async Task OutOfOrderAcknowledgementStaysPendingAndBlocksReadiness()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(
            Durable("out-of-order", "out-of-order-key", "out-of-order-body", body),
            exchangeSecret);
        var rejectingPublisher = new RejectOutOfOrderCheckpointPublisher(_fixture.Authorities);

        IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
            _fixture.AdminDataSource,
            checkpointAuthority: rejectingPublisher);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.CheckpointPending,
            (await repository.RedeemInviteAsync(mutation)).Code);

        PlayAuthorizationPostgresDormantFactory rejectingFactory =
            _fixture.CreateProviderFactory(rejectingPublisher);
        PlayAuthorizationPostgresReadinessProbe readiness = rejectingFactory.CreateReadinessProbe(
            _fixture.AdminDataSource,
            new PlayAuthorizationPostgresMigrator(_fixture.AdminDataSource),
            _fixture.Authorities,
            _fixture.PublicationPolicy,
            _fixture.ReplaySafetyPolicy,
            TimeProvider.System);
        PlayAuthorizationPostgresReadiness blocked = await readiness.CheckAsync();
        Assert.False(blocked.Ready);
        Assert.Equal("checkpoint_pending", blocked.Code);

        PlayAuthorizationCheckpointReconciliationResult recovered =
            await _fixture.CreateReconciler(_fixture.AdminDataSource).ReconcileAsync(32);
        Assert.True(recovered.Complete, recovered.Code);

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    [Fact]
    public async Task RequestCancellationAfterCommitCannotAbortCheckpointRecovery()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationRedeemMutation mutation = seed.Redeem(
            Durable("cancel-after-commit", "cancel-after-commit-key", "cancel-body", body),
            exchangeSecret);
        using var requestCancellation = new CancellationTokenSource();
        var observer = new CancelRequestAfterCommitObserver(requestCancellation);
        IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
            _fixture.AdminDataSource,
            observer);

        PlayAuthorizationPostgresMutationResult result = await repository.RedeemInviteAsync(
            mutation,
            requestCancellation.Token);

        Assert.True(requestCancellation.IsCancellationRequested);
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Applied, result.Code);
        Assert.Equal(body, result.Response?.Body);

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    [Fact]
    public async Task ReplayRequiresExactOperationAndCurrentAuthorityEpoch()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationDurableRequest durable = Durable(
            "binding-replay",
            "binding-replay-key",
            "binding-body",
            body);
        IPlayAuthorizationPostgresRepository repository =
            _fixture.CreateRepository(_fixture.AdminDataSource);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await repository.RedeemInviteAsync(seed.Redeem(durable, exchangeSecret))).Code);

        PlayAuthorizationPostgresMutationResult? wrongOperation =
            await repository.LookupIdempotencyReceiptAsync(durable with
            {
                Operation = PlayAuthorizationOperation.ConsumeExchange
            });
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict, wrongOperation?.Code);

        await using (NpgsqlConnection tamperConnection =
                     await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand tamper = tamperConnection.CreateCommand())
        {
            tamper.CommandText = """
                ALTER TABLE play_auth.audit_log DISABLE TRIGGER audit_log_append_only;
                UPDATE play_auth.audit_log
                SET operation = 'consume_exchange', epoch = 9, generation = 9
                WHERE aggregate_id = @id AND operation = 'redeem_invite';
                ALTER TABLE play_auth.audit_log ENABLE TRIGGER audit_log_append_only;
                """;
            tamper.Parameters.AddWithValue("id", seed.InviteId);
            Assert.Equal(1, await tamper.ExecuteNonQueryAsync());
        }

        PlayAuthorizationPostgresMutationResult? auditMismatch =
            await repository.LookupIdempotencyReceiptAsync(durable);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict,
            auditMismatch?.Code);

        await using (NpgsqlConnection restoreConnection =
                     await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand restore = restoreConnection.CreateCommand())
        {
            restore.CommandText = """
                ALTER TABLE play_auth.audit_log DISABLE TRIGGER audit_log_append_only;
                UPDATE play_auth.audit_log
                SET operation = 'redeem_invite', epoch = 1, generation = 1
                WHERE aggregate_id = @id AND operation = 'consume_exchange';
                ALTER TABLE play_auth.audit_log ENABLE TRIGGER audit_log_append_only;
                """;
            restore.Parameters.AddWithValue("id", seed.InviteId);
            Assert.Equal(1, await restore.ExecuteNonQueryAsync());
        }

        IPlayAuthorizationPostgresRepository wrongEpoch = _fixture.CreateRepository(
            _fixture.AdminDataSource,
            epochAuthority: new FixedEpochAuthority(
                new PlayAuthorizationExternalEpoch(2, 1, _fixture.Authorities.Checkpoint.ToArray())));
        PlayAuthorizationPostgresMutationResult? epochMismatch =
            await wrongEpoch.LookupIdempotencyReceiptAsync(durable);
        Assert.NotEqual(PlayAuthorizationPostgresOutcomeCode.Replayed, epochMismatch?.Code);
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable, epochMismatch?.Code);

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    [Fact]
    public async Task SameOperationEpochAndGenerationCannotCrossBindReceiptToAnotherAuditEvent()
    {
        SeededInvite firstSeed = await _fixture.SeedInviteAsync();
        SeededInvite secondSeed = await _fixture.SeedInviteAsync();
        byte[] firstSecret = RandomNumberGenerator.GetBytes(48);
        byte[] secondSecret = RandomNumberGenerator.GetBytes(48);
        byte[] firstBody = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{firstSeed.ExchangeId}\"}}");
        byte[] secondBody = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{secondSeed.ExchangeId}\"}}");
        PlayAuthorizationDurableRequest firstRequest = Durable(
            "cross-bind-first",
            "cross-bind-first-key",
            "cross-bind-first-body",
            firstBody);
        PlayAuthorizationDurableRequest secondRequest = Durable(
            "cross-bind-second",
            "cross-bind-second-key",
            "cross-bind-second-body",
            secondBody);
        IPlayAuthorizationPostgresRepository repository =
            _fixture.CreateRepository(_fixture.AdminDataSource);

        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await repository.RedeemInviteAsync(firstSeed.Redeem(firstRequest, firstSecret))).Code);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await repository.RedeemInviteAsync(secondSeed.Redeem(secondRequest, secondSecret))).Code);

        (long Sequence, Guid EventId, int Version, byte[] Digest) first =
            await ReadBindingAsync(firstRequest);
        (long Sequence, Guid EventId, int Version, byte[] Digest) second =
            await ReadBindingAsync(secondRequest);
        try
        {
            await using (NpgsqlConnection connection =
                         await _fixture.AdminDataSource.OpenConnectionAsync())
            await using (NpgsqlTransaction transaction = await connection.BeginTransactionAsync())
            {
                await using (NpgsqlCommand disable = connection.CreateCommand())
                {
                    disable.Transaction = transaction;
                    disable.CommandText = """
                        ALTER TABLE play_auth.idempotency_receipts
                        DISABLE TRIGGER idempotency_receipt_transition_guard
                        """;
                    await disable.ExecuteNonQueryAsync();
                }

                await using NpgsqlCommand structurallyInvalid = connection.CreateCommand();
                structurallyInvalid.Transaction = transaction;
                structurallyInvalid.CommandText = """
                    UPDATE play_auth.idempotency_receipts
                    SET audit_sequence = @sequence, audit_event_id = @event_id,
                        audit_payload_canonical_version = @version
                    WHERE scope_sha256 = @scope AND key_sha256 = @key
                    """;
                structurallyInvalid.Parameters.AddWithValue("sequence", second.Sequence);
                structurallyInvalid.Parameters.AddWithValue("event_id", second.EventId);
                structurallyInvalid.Parameters.AddWithValue("version", second.Version);
                BindReceiptIdentity(structurallyInvalid, firstRequest);
                PostgresException rejected = await Assert.ThrowsAsync<PostgresException>(
                    () => structurallyInvalid.ExecuteNonQueryAsync());
                Assert.Equal(PostgresErrorCodes.ForeignKeyViolation, rejected.SqlState);
                await transaction.RollbackAsync();
            }

            await ReplaceBindingAsync(firstRequest, second);
            PlayAuthorizationPostgresMutationResult? crossed =
                await repository.LookupIdempotencyReceiptAsync(firstRequest);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.ReceiptBindingConflict, crossed?.Code);
        }
        finally
        {
            await ReplaceBindingAsync(firstRequest, first);
            CryptographicOperations.ZeroMemory(first.Digest);
            CryptographicOperations.ZeroMemory(second.Digest);
        }

        PlayAuthorizationPostgresMutationResult? restored =
            await repository.LookupIdempotencyReceiptAsync(firstRequest);
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Replayed, restored?.Code);
        Assert.Equal(firstBody, restored?.Response?.Body);
        CryptographicOperations.ZeroMemory(firstSecret);
        CryptographicOperations.ZeroMemory(secondSecret);
        CryptographicOperations.ZeroMemory(firstBody);
        CryptographicOperations.ZeroMemory(secondBody);

        async Task<(long Sequence, Guid EventId, int Version, byte[] Digest)> ReadBindingAsync(
            PlayAuthorizationDurableRequest request)
        {
            await using NpgsqlConnection connection =
                await _fixture.AdminDataSource.OpenConnectionAsync();
            await using NpgsqlCommand command = connection.CreateCommand();
            command.CommandText = """
                SELECT audit_sequence, audit_event_id,
                       audit_payload_canonical_version, audited_payload_sha256
                FROM play_auth.idempotency_receipts
                WHERE scope_sha256 = @scope AND key_sha256 = @key
                """;
            BindReceiptIdentity(command, request);
            await using NpgsqlDataReader reader = await command.ExecuteReaderAsync();
            Assert.True(await reader.ReadAsync());
            return (
                reader.GetInt64(0),
                reader.GetGuid(1),
                reader.GetInt32(2),
                ((byte[])reader[3]).ToArray());
        }

        async Task ReplaceBindingAsync(
            PlayAuthorizationDurableRequest request,
            (long Sequence, Guid EventId, int Version, byte[] Digest) binding)
        {
            await using NpgsqlConnection connection =
                await _fixture.AdminDataSource.OpenConnectionAsync();
            await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync();
            await using NpgsqlCommand command = connection.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = """
                ALTER TABLE play_auth.idempotency_receipts
                DISABLE TRIGGER idempotency_receipt_transition_guard;
                UPDATE play_auth.idempotency_receipts
                SET audit_sequence = @sequence, audit_event_id = @event_id,
                    audit_payload_canonical_version = @version,
                    audited_payload_sha256 = @digest
                WHERE scope_sha256 = @scope AND key_sha256 = @key;
                ALTER TABLE play_auth.idempotency_receipts
                ENABLE TRIGGER idempotency_receipt_transition_guard
                """;
            command.Parameters.AddWithValue("sequence", binding.Sequence);
            command.Parameters.AddWithValue("event_id", binding.EventId);
            command.Parameters.AddWithValue("version", binding.Version);
            command.Parameters.AddWithValue("digest", NpgsqlDbType.Bytea, binding.Digest);
            BindReceiptIdentity(command, request);
            Assert.Equal(1, await command.ExecuteNonQueryAsync());
            await transaction.CommitAsync();
        }

        static void BindReceiptIdentity(
            NpgsqlCommand command,
            PlayAuthorizationDurableRequest request)
        {
            command.Parameters.AddWithValue(
                "scope",
                NpgsqlDbType.Bytea,
                SHA256.HashData(Encoding.UTF8.GetBytes(request.Scope)));
            command.Parameters.AddWithValue(
                "key",
                NpgsqlDbType.Bytea,
                SHA256.HashData(Encoding.UTF8.GetBytes(request.IdempotencyKey)));
        }
    }

    [Fact]
    public async Task ExpiryLookupAndPruneRaceNeverReplaysAndKeyReusesOnlyAfterQuarantineDelete()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        PlayAuthorizationDurableRequest durable = Durable(
            "expiry-prune",
            "expiry-prune-key",
            "expiry-prune-body",
            body);
        IPlayAuthorizationPostgresRepository repository =
            _fixture.CreateRepository(_fixture.AdminDataSource);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await repository.RedeemInviteAsync(seed.Redeem(durable, exchangeSecret))).Code);

        DateTimeOffset originalHighWater;
        DateTimeOffset receiptExpiry;
        await using (NpgsqlConnection connection = await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand read = connection.CreateCommand())
        {
            read.CommandText = """
                SELECT authority.clock_high_water_utc, receipt.expires_at_utc
                FROM play_auth.authority_state AS authority
                JOIN play_auth.idempotency_receipts AS receipt ON true
                WHERE authority.singleton = true
                  AND receipt.scope_sha256 = @scope
                  AND receipt.key_sha256 = @key
                """;
            read.Parameters.AddWithValue(
                "scope",
                NpgsqlDbType.Bytea,
                SHA256.HashData(Encoding.UTF8.GetBytes(durable.Scope)));
            read.Parameters.AddWithValue(
                "key",
                NpgsqlDbType.Bytea,
                SHA256.HashData(Encoding.UTF8.GetBytes(durable.IdempotencyKey)));
            await using NpgsqlDataReader reader = await read.ExecuteReaderAsync();
            Assert.True(await reader.ReadAsync());
            originalHighWater = reader.GetFieldValue<DateTimeOffset>(0);
            receiptExpiry = reader.GetFieldValue<DateTimeOffset>(1);
        }

        var pruner = new NpgsqlPlayAuthorizationIdempotencyReceiptPruner(
            _fixture.AdminDataSource,
            _fixture.ReplaySafetyPolicy.MinimumQuarantine,
            _fixture.ReplaySafetyPolicy,
            TimeProvider.System);
        try
        {
            await SetHighWaterAsync(receiptExpiry.AddSeconds(1));
            Task<PlayAuthorizationPostgresMutationResult?> lookup =
                repository.LookupIdempotencyReceiptAsync(durable);
            Task<PlayAuthorizationReceiptPruneResult> prune = pruner.PruneExpiredAsync(1000);
            await Task.WhenAll(lookup, prune);
            PlayAuthorizationPostgresMutationResult? lookupResult = await lookup;
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Expired, lookupResult?.Code);

            await using (NpgsqlConnection connection = await _fixture.AdminDataSource.OpenConnectionAsync())
            await using (NpgsqlCommand scrubbed = connection.CreateCommand())
            {
                scrubbed.CommandText = """
                    SELECT state, response_ciphertext IS NULL, quarantine_until_utc,
                           audit_sequence IS NULL, audit_event_id IS NULL,
                           audit_payload_canonical_version IS NULL,
                           audited_payload_sha256 IS NULL
                    FROM play_auth.idempotency_receipts
                    WHERE scope_sha256 = @scope AND key_sha256 = @key
                    """;
                scrubbed.Parameters.AddWithValue(
                    "scope",
                    NpgsqlDbType.Bytea,
                    SHA256.HashData(Encoding.UTF8.GetBytes(durable.Scope)));
                scrubbed.Parameters.AddWithValue(
                    "key",
                    NpgsqlDbType.Bytea,
                    SHA256.HashData(Encoding.UTF8.GetBytes(durable.IdempotencyKey)));
                await using NpgsqlDataReader reader = await scrubbed.ExecuteReaderAsync();
                Assert.True(await reader.ReadAsync());
                Assert.Equal("pruned", reader.GetString(0));
                Assert.True(reader.GetBoolean(1));
                DateTimeOffset quarantineUntil = reader.GetFieldValue<DateTimeOffset>(2);
                Assert.True(reader.GetBoolean(3));
                Assert.True(reader.GetBoolean(4));
                Assert.True(reader.GetBoolean(5));
                Assert.True(reader.GetBoolean(6));
                await reader.DisposeAsync();

                await SetHighWaterAsync(quarantineUntil.AddSeconds(1));
            }

            PlayAuthorizationReceiptPruneResult deletion = await pruner.PruneExpiredAsync(1000);
            Assert.True(deletion.DeletedCount >= 1);
            Assert.Null(await repository.LookupIdempotencyReceiptAsync(durable));
        }
        finally
        {
            await SetHighWaterAsync(originalHighWater);
        }

        SeededInvite reuseSeed = await _fixture.SeedInviteAsync();
        byte[] replacementSecret = RandomNumberGenerator.GetBytes(48);
        byte[] replacementBody = Encoding.UTF8.GetBytes(
            $"{{\"exchangeId\":\"{reuseSeed.ExchangeId}\"}}");
        PlayAuthorizationDurableRequest reused = Durable(
            durable.Scope,
            durable.IdempotencyKey,
            "replacement-fingerprint",
            replacementBody);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await repository.RedeemInviteAsync(reuseSeed.Redeem(reused, replacementSecret))).Code);

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(replacementSecret);
        CryptographicOperations.ZeroMemory(body);
        CryptographicOperations.ZeroMemory(replacementBody);

        async Task SetHighWaterAsync(DateTimeOffset value)
        {
            await using NpgsqlConnection connection = await _fixture.AdminDataSource.OpenConnectionAsync();
            await using NpgsqlCommand command = connection.CreateCommand();
            command.CommandText = """
                UPDATE play_auth.authority_state
                SET clock_high_water_utc = @value, updated_at_utc = @value
                WHERE singleton = true
                """;
            command.Parameters.AddWithValue("value", value);
            Assert.Equal(1, await command.ExecuteNonQueryAsync());
        }
    }

    [Fact]
    public void CanonicalCheckpointDigestBindsEveryStableEnvelopeFieldAndExcludesFence()
    {
        Guid publicationId = Guid.NewGuid();
        var state = new PlayAuthorizationPostgresState(
            7,
            11,
            new DateTimeOffset(2030, 4, 5, 6, 7, 8, TimeSpan.Zero),
            13,
            Enumerable.Repeat((byte)0x31, 32).ToArray(),
            Enumerable.Repeat((byte)0x73, 48).ToArray());
        byte[] expected = Digest(publicationId, state);
        var firstEnvelope = new PlayAuthorizationCheckpointPublicationEnvelope(
            publicationId,
            1,
            state,
            PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
            PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
            expected);
        var retryEnvelope = firstEnvelope with { FencingToken = 999 };
        Assert.Same(expected, retryEnvelope.PayloadDigestSha256);

        AssertChanged(Guid.NewGuid(), state);
        AssertChanged(publicationId, state with { Epoch = state.Epoch + 1 });
        AssertChanged(publicationId, state with { Generation = state.Generation + 1 });
        AssertChanged(publicationId, state with { AuditHeadSequence = state.AuditHeadSequence + 1 });
        AssertChanged(publicationId, state with { ClockHighWaterUtc = state.ClockHighWaterUtc.AddTicks(1) });
        AssertChanged(publicationId, state with
        {
            AuditHeadHmac = state.AuditHeadHmac.Select((value, index) =>
                index == 0 ? (byte)(value ^ 0xff) : value).ToArray()
        });
        AssertChanged(publicationId, state with
        {
            ExternalCheckpoint = state.ExternalCheckpoint.Select((value, index) =>
                index == 0 ? (byte)(value ^ 0xff) : value).ToArray()
        });
        Assert.Throws<ArgumentException>(() =>
            PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                publicationId,
                state,
                "sha-256",
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion));
        Assert.Throws<ArgumentException>(() =>
            PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                publicationId,
                state,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion + 1));
        var oversizedHmacState = state with
        {
            AuditHeadHmac = Enumerable.Repeat((byte)0x41, 64).ToArray()
        };
        Assert.Throws<ArgumentException>(() => Digest(publicationId, oversizedHmacState));
        CryptographicOperations.ZeroMemory(oversizedHmacState.AuditHeadHmac);

        CryptographicOperations.ZeroMemory(expected);
        CryptographicOperations.ZeroMemory(state.AuditHeadHmac);
        CryptographicOperations.ZeroMemory(state.ExternalCheckpoint);

        void AssertChanged(Guid id, PlayAuthorizationPostgresState changed)
        {
            byte[] actual = Digest(id, changed);
            try
            {
                Assert.False(CryptographicOperations.FixedTimeEquals(expected, actual));
            }
            finally
            {
                CryptographicOperations.ZeroMemory(actual);
            }
        }

        static byte[] Digest(Guid id, PlayAuthorizationPostgresState value)
            => PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
                id,
                value,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion);
    }

    [Fact]
    public void LineageCapacityAcceptsTenThousandAndBlocksTenThousandAndOne()
    {
        Assert.Equal(10_000, PlayAuthorizationPostgresReadinessProbe.MaximumLineageProofRows);
        Assert.False(PlayAuthorizationPostgresReadinessProbe.ExceedsLineageProofCapacity(7, 10_007));
        Assert.True(PlayAuthorizationPostgresReadinessProbe.ExceedsLineageProofCapacity(7, 10_008));
    }

    [Fact]
    public void CanonicalAuditPayloadMatchesIndependentVectorAndBindsEveryVersionedField()
    {
        Guid eventId = Guid.Parse("00112233-4455-6677-8899-aabbccddeeff");
        const long Epoch = 1;
        const long Generation = 2;
        const long Sequence = 3;
        const string Operation = "redeem_invite";
        const string AggregateKind = "invite";
        const string AggregateId = "invite-fixed-vector";
        const string ActorDigest =
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        const int Version = PlayAuthorizationPostgresDurabilityInvariants.AuditPayloadCanonicalVersion;
        byte[] scope = Enumerable.Repeat((byte)0x11, 32).ToArray();
        byte[] key = Enumerable.Repeat((byte)0x22, 32).ToArray();
        byte[] fingerprint = Enumerable.Repeat((byte)0x33, 32).ToArray();
        byte[] response = Enumerable.Repeat((byte)0x44, 32).ToArray();
        // Independently generated from the documented network-order byte layout.
        byte[] expected = Convert.FromHexString(
            "229af8cfaacc26ced110488854b15de557e1fcd5edec6222ef72f2f63503d585");
        byte[] actual = Digest(
            eventId,
            Epoch,
            Generation,
            Sequence,
            Operation,
            AggregateKind,
            AggregateId,
            ActorDigest,
            scope,
            key,
            fingerprint,
            response,
            Version);
        try
        {
            Assert.True(CryptographicOperations.FixedTimeEquals(expected, actual));
            AssertChanged(() => Digest(
                Guid.Parse("10112233-4455-6677-8899-aabbccddeeff"), Epoch, Generation,
                Sequence, Operation, AggregateKind, AggregateId, ActorDigest,
                scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch + 1, Generation, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest, scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch, Generation + 1, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest, scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch, Generation, Sequence + 1, Operation, AggregateKind,
                AggregateId, ActorDigest, scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch, Generation, Sequence, "close_session", AggregateKind,
                AggregateId, ActorDigest, scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch, Generation, Sequence, Operation, "session",
                AggregateId, ActorDigest, scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                "invite-fixed-vector-changed", ActorDigest,
                scope, key, fingerprint, response, Version));
            AssertChanged(() => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                AggregateId, new string('f', 64),
                scope, key, fingerprint, response, Version));

            AssertChangedDigest(scope, changedScope => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest,
                changedScope, key, fingerprint, response, Version));
            AssertChangedDigest(key, changedKey => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest,
                scope, changedKey, fingerprint, response, Version));
            AssertChangedDigest(fingerprint, changedFingerprint => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest,
                scope, key, changedFingerprint, response, Version));
            AssertChangedDigest(response, changedResponse => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest,
                scope, key, fingerprint, changedResponse, Version));

            Assert.Throws<ArgumentException>(() => Digest(
                eventId, Epoch, Generation, Sequence, Operation, AggregateKind,
                AggregateId, ActorDigest,
                scope, key, fingerprint, response, Version + 1));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(scope);
            CryptographicOperations.ZeroMemory(key);
            CryptographicOperations.ZeroMemory(fingerprint);
            CryptographicOperations.ZeroMemory(response);
            CryptographicOperations.ZeroMemory(expected);
            CryptographicOperations.ZeroMemory(actual);
        }

        void AssertChanged(Func<byte[]> calculate)
        {
            byte[] changed = calculate();
            try
            {
                Assert.False(CryptographicOperations.FixedTimeEquals(expected, changed));
            }
            finally
            {
                CryptographicOperations.ZeroMemory(changed);
            }
        }

        void AssertChangedDigest(byte[] source, Func<byte[], byte[]> calculate)
        {
            byte[] changed = source.ToArray();
            changed[0] ^= 0xff;
            try
            {
                AssertChanged(() => calculate(changed));
            }
            finally
            {
                CryptographicOperations.ZeroMemory(changed);
            }
        }

        static byte[] Digest(
            Guid id,
            long epoch,
            long generation,
            long sequence,
            string operation,
            string aggregateKind,
            string aggregateId,
            string actorDigest,
            byte[] scopeValue,
            byte[] keyValue,
            byte[] fingerprintValue,
            byte[] responseValue,
            int version)
            => PlayAuthorizationAuditPayloadCanonicalizer.ComputePayloadDigest(
                id,
                epoch,
                generation,
                sequence,
                operation,
                aggregateKind,
                aggregateId,
                actorDigest,
                scopeValue,
                keyValue,
                fingerprintValue,
                responseValue,
                version);
    }

    [Fact]
    public async Task CheckpointProviderRejectsStaleFenceAndAcceptsHigherRetryForStableDigest()
    {
        using var authority = new EphemeralTestAuthorities();
        Guid publicationId = Guid.NewGuid();
        var state = new PlayAuthorizationPostgresState(
            1,
            1,
            DateTimeOffset.UtcNow,
            1,
            RandomNumberGenerator.GetBytes(32),
            authority.Checkpoint.ToArray());
        byte[] digest = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
            publicationId,
            state,
            authority.Capabilities.DigestAlgorithm,
            authority.Capabilities.CanonicalVersion);
        try
        {
            PlayAuthorizationCheckpointPublicationAcknowledgement accepted =
                await authority.PublishAsync(
                    new(publicationId, 2, state, authority.Capabilities.DigestAlgorithm,
                        authority.Capabilities.CanonicalVersion, digest),
                    CancellationToken.None);
            Assert.Equal(PlayAuthorizationCheckpointPublicationDisposition.Accepted, accepted.Disposition);

            PlayAuthorizationCheckpointPublicationAcknowledgement stale =
                await authority.PublishAsync(
                    new(publicationId, 1, state, authority.Capabilities.DigestAlgorithm,
                        authority.Capabilities.CanonicalVersion, digest),
                    CancellationToken.None);
            Assert.Equal(
                PlayAuthorizationCheckpointPublicationDisposition.RejectedOutOfOrder,
                stale.Disposition);

            PlayAuthorizationCheckpointPublicationAcknowledgement retry =
                await authority.PublishAsync(
                    new(publicationId, 3, state, authority.Capabilities.DigestAlgorithm,
                        authority.Capabilities.CanonicalVersion, digest),
                    CancellationToken.None);
            Assert.Equal(
                PlayAuthorizationCheckpointPublicationDisposition.AlreadyPublished,
                retry.Disposition);
            Assert.Equal(3, retry.AcceptedFencingToken);
            Assert.True(CryptographicOperations.FixedTimeEquals(digest, retry.PayloadDigestSha256));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(digest);
            CryptographicOperations.ZeroMemory(state.AuditHeadHmac);
            CryptographicOperations.ZeroMemory(state.ExternalCheckpoint);
        }
    }

    [Fact]
    public void V004UpgradeQuarantinesOnlyCurrentHeadAndSynthesizesNoHistoricalPublications()
    {
        PlayAuthorizationPostgresMigration migration =
            Assert.Single(PlayAuthorizationPostgresMigrationCatalog.Load(), item => item.Version == 4);
        Assert.Contains("CREATE TABLE play_auth.checkpoint_baseline", migration.Sql, StringComparison.Ordinal);
        Assert.Contains("FROM play_auth.authority_state", migration.Sql, StringComparison.Ordinal);
        Assert.Contains("state, captured_at_utc", migration.Sql, StringComparison.Ordinal);
        Assert.Contains("WITH migration_clock AS MATERIALIZED", migration.Sql, StringComparison.Ordinal);
        Assert.Contains(
            "GREATEST(clock_timestamp(), authority.clock_high_water_utc)",
            migration.Sql,
            StringComparison.Ordinal);
        Assert.Contains("pruned_at_utc >= expires_at_utc", migration.Sql, StringComparison.Ordinal);
        Assert.Contains("MATCH FULL", migration.Sql, StringComparison.Ordinal);
        Assert.DoesNotContain(
            "INSERT INTO play_auth.checkpoint_publications\nSELECT",
            migration.Sql,
            StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(
            "FROM play_auth.audit_log\nWHERE",
            migration.Sql,
            StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task MultiEpochUpgradeQuarantinesLegacyReceiptsUntilFutureSafeDeleteBoundary()
    {
        string databaseName = $"play_upgrade_{Guid.NewGuid():N}";
        await using (NpgsqlConnection admin = await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand create = admin.CreateCommand())
        {
            create.CommandText = $"CREATE DATABASE \"{databaseName}\"";
            await create.ExecuteNonQueryAsync();
        }

        var builder = new NpgsqlConnectionStringBuilder(_fixture.ConnectionString)
        {
            Database = databaseName
        };
        try
        {
            await using NpgsqlDataSource upgradeDataSource = NpgsqlDataSource.Create(builder.ConnectionString);
            IReadOnlyList<PlayAuthorizationPostgresMigration> migrations =
                PlayAuthorizationPostgresMigrationCatalog.Load();
            await using (NpgsqlConnection connection = await upgradeDataSource.OpenConnectionAsync())
            {
                await using (NpgsqlCommand bootstrap = connection.CreateCommand())
                {
                    bootstrap.CommandText = """
                        CREATE SCHEMA IF NOT EXISTS play_auth;
                        CREATE TABLE play_auth.schema_migrations (
                            version integer PRIMARY KEY CHECK (version > 0),
                            name text NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 256),
                            checksum_sha256 text NOT NULL CHECK (checksum_sha256 ~ '^[0-9a-f]{64}$'),
                            applied_at_utc timestamptz NOT NULL DEFAULT clock_timestamp())
                        """;
                    await bootstrap.ExecuteNonQueryAsync();
                }

                foreach (PlayAuthorizationPostgresMigration migration in migrations.Where(
                             item => item.Version <= 3))
                {
                    await using NpgsqlTransaction migrationTransaction =
                        await connection.BeginTransactionAsync();
                    await using NpgsqlCommand apply = connection.CreateCommand();
                    apply.Transaction = migrationTransaction;
                    apply.CommandText = migration.Sql;
                    await apply.ExecuteNonQueryAsync();
                    await using NpgsqlCommand record = connection.CreateCommand();
                    record.Transaction = migrationTransaction;
                    record.CommandText = """
                        INSERT INTO play_auth.schema_migrations(version, name, checksum_sha256)
                        VALUES (@version, @name, @checksum)
                        """;
                    record.Parameters.AddWithValue("version", migration.Version);
                    record.Parameters.AddWithValue("name", migration.Name);
                    record.Parameters.AddWithValue("checksum", migration.ChecksumSha256);
                    await record.ExecuteNonQueryAsync();
                    await migrationTransaction.CommitAsync();
                }

                await using (NpgsqlCommand seed = connection.CreateCommand())
                {
                    seed.CommandText = """
                        UPDATE play_auth.authority_state
                        SET epoch = 1, generation = 1,
                            clock_high_water_utc = TIMESTAMPTZ '2099-01-01 00:00:00+00',
                            external_checkpoint = decode(repeat('11', 32), 'hex'),
                            updated_at_utc = TIMESTAMPTZ '2099-01-01 00:00:00+00'
                        WHERE singleton = true;

                        INSERT INTO play_auth.audit_log(
                            sequence, event_id, epoch, generation, operation, aggregate_kind,
                            aggregate_id, actor_digest_sha256, payload_sha256, previous_hmac,
                            entry_hmac, hmac_key_id, occurred_at_utc)
                        VALUES (1, gen_random_uuid(), 1, 1, 'redeem_invite', 'invite',
                            'legacy-epoch-one', repeat('a', 64),
                            decode(repeat('01', 32), 'hex'), decode(repeat('00', 32), 'hex'),
                            decode(repeat('31', 32), 'hex'), 'legacy-key',
                            TIMESTAMPTZ '2099-01-01 00:00:01+00');

                        UPDATE play_auth.authority_state
                        SET audit_head_sequence = 1,
                            audit_head_hmac = decode(repeat('31', 32), 'hex'),
                            epoch = 2, generation = 3,
                            clock_high_water_utc = TIMESTAMPTZ '2099-02-01 00:00:00+00',
                            external_checkpoint = decode(repeat('22', 32), 'hex'),
                            updated_at_utc = TIMESTAMPTZ '2099-02-01 00:00:00+00'
                        WHERE singleton = true;

                        INSERT INTO play_auth.audit_log(
                            sequence, event_id, epoch, generation, operation, aggregate_kind,
                            aggregate_id, actor_digest_sha256, payload_sha256, previous_hmac,
                            entry_hmac, hmac_key_id, occurred_at_utc)
                        VALUES (2, gen_random_uuid(), 2, 3, 'close_session', 'session',
                            'current-epoch-two', repeat('b', 64),
                            decode(repeat('02', 32), 'hex'), decode(repeat('31', 32), 'hex'),
                            decode(repeat('42', 32), 'hex'), 'current-key',
                            TIMESTAMPTZ '2099-02-01 00:00:01+00');

                        UPDATE play_auth.authority_state
                        SET audit_head_sequence = 2,
                            audit_head_hmac = decode(repeat('42', 32), 'hex')
                        WHERE singleton = true;

                        INSERT INTO play_auth.idempotency_receipts(
                            scope_sha256, key_sha256, fingerprint_sha256, operation, state,
                            epoch, generation, response_type, response_status,
                            response_ciphertext, response_plaintext_sha256,
                            created_at_utc, completed_at_utc, expires_at_utc)
                        VALUES (
                            decode(repeat('51', 32), 'hex'), decode(repeat('52', 32), 'hex'),
                            decode(repeat('53', 32), 'hex'), 'redeem_invite', 'completed',
                            2, 3, 'ExchangeIssued', 201, decode('01', 'hex'),
                            decode(repeat('54', 32), 'hex'),
                            TIMESTAMPTZ '2099-02-01 00:00:02+00',
                            TIMESTAMPTZ '2099-02-01 00:00:03+00',
                            TIMESTAMPTZ '2099-03-01 00:00:00+00'),
                            (
                            decode(repeat('61', 32), 'hex'), decode(repeat('62', 32), 'hex'),
                            decode(repeat('63', 32), 'hex'), 'close_session', 'in_progress',
                            2, 3, NULL, NULL, NULL, NULL,
                            TIMESTAMPTZ '2099-02-01 00:00:04+00', NULL,
                            TIMESTAMPTZ '2099-03-01 00:00:00+00');
                        """;
                    await seed.ExecuteNonQueryAsync();
                }

                var upgradeMigrator = new PlayAuthorizationPostgresMigrator(upgradeDataSource);
                await upgradeMigrator.MigrateAsync();

                await using NpgsqlCommand verify = connection.CreateCommand();
                verify.CommandText = """
                    SELECT baseline.state, baseline.epoch, baseline.generation,
                           baseline.audit_head_sequence,
                           baseline.audit_head_hmac = decode(repeat('42', 32), 'hex'),
                           baseline.external_checkpoint = decode(repeat('22', 32), 'hex'),
                           (SELECT COUNT(*) FROM play_auth.checkpoint_publications),
                           (SELECT COUNT(*) FROM play_auth.schema_migrations WHERE version = 4),
                           (SELECT COUNT(*)
                            FROM play_auth.idempotency_receipts AS receipt
                            WHERE receipt.state = 'pruned'
                              AND receipt.response_type IS NULL
                              AND receipt.response_status IS NULL
                              AND receipt.response_ciphertext IS NULL
                              AND receipt.response_plaintext_sha256 IS NULL
                              AND receipt.audit_sequence IS NULL
                              AND receipt.audit_event_id IS NULL
                              AND receipt.audit_payload_canonical_version IS NULL
                              AND receipt.audited_payload_sha256 IS NULL
                              AND receipt.quarantine_until_utc
                                  = receipt.pruned_at_utc + INTERVAL '365 days')
                    FROM play_auth.checkpoint_baseline AS baseline
                    WHERE baseline.singleton = true
                    """;
                await using NpgsqlDataReader reader = await verify.ExecuteReaderAsync();
                Assert.True(await reader.ReadAsync());
                Assert.Equal("quarantined", reader.GetString(0));
                Assert.Equal(2, reader.GetInt64(1));
                Assert.Equal(3, reader.GetInt64(2));
                Assert.Equal(2, reader.GetInt64(3));
                Assert.True(reader.GetBoolean(4));
                Assert.True(reader.GetBoolean(5));
                Assert.Equal(0, reader.GetInt64(6));
                Assert.Equal(1, reader.GetInt64(7));
                Assert.Equal(2, reader.GetInt64(8));
                await reader.DisposeAsync();

                DateTimeOffset expiresAt;
                DateTimeOffset prunedAt;
                DateTimeOffset quarantineUntil;
                await using (NpgsqlCommand boundary = connection.CreateCommand())
                {
                    boundary.CommandText = """
                        SELECT expires_at_utc, pruned_at_utc, quarantine_until_utc
                        FROM play_auth.idempotency_receipts
                        WHERE scope_sha256 = decode(repeat('51', 32), 'hex')
                          AND key_sha256 = decode(repeat('52', 32), 'hex')
                        """;
                    await using NpgsqlDataReader boundaryReader =
                        await boundary.ExecuteReaderAsync();
                    Assert.True(await boundaryReader.ReadAsync());
                    expiresAt = boundaryReader.GetFieldValue<DateTimeOffset>(0);
                    prunedAt = boundaryReader.GetFieldValue<DateTimeOffset>(1);
                    quarantineUntil = boundaryReader.GetFieldValue<DateTimeOffset>(2);
                }

                Assert.Equal(expiresAt, prunedAt);
                Assert.Equal(prunedAt.AddDays(365), quarantineUntil);

                await using (NpgsqlCommand blockedDelete = connection.CreateCommand())
                {
                    blockedDelete.CommandText = """
                        DELETE FROM play_auth.idempotency_receipts
                        WHERE scope_sha256 = decode(repeat('51', 32), 'hex')
                          AND key_sha256 = decode(repeat('52', 32), 'hex')
                        """;
                    PostgresException blocked = await Assert.ThrowsAsync<PostgresException>(
                        () => blockedDelete.ExecuteNonQueryAsync());
                    Assert.Equal("55000", blocked.SqlState);
                }

                await using (NpgsqlCommand advanceClock = connection.CreateCommand())
                {
                    advanceClock.CommandText = """
                        UPDATE play_auth.authority_state
                        SET clock_high_water_utc = @boundary,
                            updated_at_utc = @boundary
                        WHERE singleton = true
                        """;
                    advanceClock.Parameters.AddWithValue(
                        "boundary",
                        quarantineUntil.AddSeconds(1));
                    Assert.Equal(1, await advanceClock.ExecuteNonQueryAsync());
                }

                await using (NpgsqlCommand allowedDelete = connection.CreateCommand())
                {
                    allowedDelete.CommandText = """
                        DELETE FROM play_auth.idempotency_receipts
                        WHERE scope_sha256 = decode(repeat('51', 32), 'hex')
                          AND key_sha256 = decode(repeat('52', 32), 'hex')
                        """;
                    Assert.Equal(1, await allowedDelete.ExecuteNonQueryAsync());
                }
            }
        }
        finally
        {
            await using NpgsqlConnection admin = await _fixture.AdminDataSource.OpenConnectionAsync();
            await using NpgsqlCommand drop = admin.CreateCommand();
            drop.CommandText = $"DROP DATABASE IF EXISTS \"{databaseName}\" WITH (FORCE)";
            await drop.ExecuteNonQueryAsync();
        }
    }

    [Fact]
    public async Task AuthorityRotationDuringExternalAuditPreparationCommitsNothing()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        var rotating = new RotateAuthorityDuringAuditAuthority(
            _fixture.Authorities,
            _fixture.AdminDataSource);
        IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
            _fixture.AdminDataSource,
            hmacAuthority: rotating);
        try
        {
            PlayAuthorizationPostgresMutationResult result = await repository.RedeemInviteAsync(
                seed.Redeem(
                    Durable("rotation-race", "rotation-race-key", "rotation-race-body", body),
                    exchangeSecret));
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable, result.Code);
            Assert.Equal(0, await _fixture.CountAsync(
                "SELECT COUNT(*) FROM play_auth.exchanges WHERE exchange_id = @id",
                seed.ExchangeId));
            Assert.Equal(0, await _fixture.CountAsync(
                "SELECT COUNT(*) FROM play_auth.audit_log WHERE aggregate_id = @id",
                seed.InviteId));
        }
        finally
        {
            await rotating.RestoreAsync();
            CryptographicOperations.ZeroMemory(exchangeSecret);
            CryptographicOperations.ZeroMemory(body);
        }
    }

    [Fact]
    public async Task NonCooperativePublicationIsProcessSingleFlightAcrossReconcilersAndRecovers()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        var provider = new IgnoringCancellationCheckpointPublisher(
            _fixture.Authorities,
            TimeSpan.FromMilliseconds(40));
        var policy = new PlayAuthorizationCheckpointPublicationPolicy(
            claimLease: TimeSpan.FromMilliseconds(750),
            databaseFinalizationDeadline: TimeSpan.FromMilliseconds(200),
            clockSkew: TimeSpan.FromMilliseconds(20));
        PlayAuthorizationPostgresDormantFactory providerFactory =
            _fixture.CreateProviderFactory(provider).BindCheckpointReconciliation(
                _fixture.AdminDataSource,
                _fixture.Authorities,
                policy,
                TimeProvider.System);
        PlayAuthorizationPostgresDormantFactory second =
            _fixture.CreateProviderFactory(provider).BindCheckpointReconciliation(
                _fixture.AdminDataSource,
                _fixture.Authorities,
                policy,
                TimeProvider.System);
        PlayAuthorizationPostgresDormantFactory first = providerFactory;
        try
        {
            IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
                _fixture.AdminDataSource,
                providerFactory: first,
                publicationPolicy: policy);
            PlayAuthorizationPostgresMutationResult pending = await repository.RedeemInviteAsync(
                seed.Redeem(
                    Durable(
                        "single-flight-provider",
                        "single-flight-provider-key",
                        "single-flight-provider-body",
                        body),
                    exchangeSecret));
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.CheckpointPending, pending.Code);
            Assert.Equal(1, provider.PublishInvocationCount);
            Assert.Equal(1, first.ProviderCallDiagnostics.PublicationCallsInFlight);
            Assert.Equal(1, second.ProviderCallDiagnostics.PublicationCallsInFlight);
            Assert.Equal(1, second.ProviderCallDiagnostics.TotalCallsInFlight);

            PlayAuthorizationPostgresReadinessProbe readiness =
                providerFactory.CreateReadinessProbe(
                    _fixture.AdminDataSource,
                    new PlayAuthorizationPostgresMigrator(_fixture.AdminDataSource),
                    _fixture.Authorities,
                    policy,
                    _fixture.ReplaySafetyPolicy,
                    TimeProvider.System);
            PlayAuthorizationPostgresReadiness blocked = await readiness.CheckAsync();
            Assert.False(blocked.Ready);
            Assert.Equal("checkpoint_provider_call_in_flight", blocked.Code);

            await Task.Delay(policy.ClaimLease + TimeSpan.FromMilliseconds(150));
            for (int attempt = 0; attempt < 8; attempt++)
            {
                PlayAuthorizationPostgresDormantFactory reconciler =
                    attempt % 2 == 0 ? first : second;
                PlayAuthorizationCheckpointReconciliationResult retained =
                    await reconciler.ReconcileAsync(1);
                Assert.False(retained.Complete);
                Assert.Equal("publication_provider_call_in_flight", retained.Code);
                Assert.Equal(1, provider.PublishInvocationCount);
                Assert.Equal(1, reconciler.ProviderCallDiagnostics.TotalCallsInFlight);
            }

            await provider.ReleaseAsync();
            for (int attempt = 0;
                 attempt < 50 && second.ProviderCallDiagnostics.TotalCallsInFlight != 0;
                 attempt++)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(10));
            }

            Assert.Equal(0, first.ProviderCallDiagnostics.TotalCallsInFlight);
            Assert.Equal(0, second.ProviderCallDiagnostics.TotalCallsInFlight);
            PlayAuthorizationCheckpointReconciliationResult recovered =
                await second.ReconcileAsync(1);
            Assert.True(recovered.Complete, recovered.Code);
            Assert.Equal(2, provider.PublishInvocationCount);
            Assert.Equal(0, second.ProviderCallDiagnostics.TotalCallsInFlight);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(exchangeSecret);
            CryptographicOperations.ZeroMemory(body);
        }
    }

    [Fact]
    public async Task NonCooperativeValidationIsSingleFlightOwnedAndReentrantWithoutMonitorDeadlock()
    {
        SeededInvite replaySeed = await _fixture.SeedInviteAsync();
        byte[] replaySecret = RandomNumberGenerator.GetBytes(48);
        byte[] replayBody = Encoding.UTF8.GetBytes(
            $"{{\"exchangeId\":\"{replaySeed.ExchangeId}\"}}");
        PlayAuthorizationDurableRequest replayRequest = Durable(
            "validation-single-flight-replay",
            "validation-single-flight-replay-key",
            "validation-single-flight-replay-body",
            replayBody);
        Assert.Equal(
            PlayAuthorizationPostgresOutcomeCode.Applied,
            (await _fixture.CreateRepository(_fixture.AdminDataSource).RedeemInviteAsync(
                replaySeed.Redeem(replayRequest, replaySecret))).Code);

        SeededInvite mutationSeed = await _fixture.SeedInviteAsync();
        byte[] mutationSecret = RandomNumberGenerator.GetBytes(48);
        byte[] mutationBody = Encoding.UTF8.GetBytes(
            $"{{\"exchangeId\":\"{mutationSeed.ExchangeId}\"}}");
        var provider = new SynchronouslyBlockingCheckpointValidationAuthority(
            _fixture.Authorities,
            TimeSpan.FromMilliseconds(40));
        PlayAuthorizationPostgresDormantFactory providerFactory =
            _fixture.CreateProviderFactory(provider).BindCheckpointReconciliation(
                _fixture.AdminDataSource,
                _fixture.Authorities,
                _fixture.PublicationPolicy,
                TimeProvider.System);
        PlayAuthorizationPostgresDormantFactory second =
            _fixture.CreateProviderFactory(provider).BindCheckpointReconciliation(
                _fixture.AdminDataSource,
                _fixture.Authorities,
                _fixture.PublicationPolicy,
                TimeProvider.System);
        PlayAuthorizationPostgresDormantFactory first = providerFactory;
        provider.SynchronousPrefix = () =>
        {
            provider.ReentrantValidationCallsInFlight =
                second.ProviderCallDiagnostics.ValidationCallsInFlight;
            PlayAuthorizationCheckpointReconciliationResult reentrant =
                second.ReconcileAsync(1).GetAwaiter().GetResult();
            provider.ReentrantReconciliationCode = reentrant.Code;
        };
        PlayAuthorizationPostgresReadinessProbe readiness =
            providerFactory.CreateReadinessProbe(
                _fixture.AdminDataSource,
                new PlayAuthorizationPostgresMigrator(_fixture.AdminDataSource),
                _fixture.Authorities,
                _fixture.PublicationPolicy,
                _fixture.ReplaySafetyPolicy,
                TimeProvider.System);
        try
        {
            PlayAuthorizationPostgresReadiness timedOut = await readiness
                .CheckAsync()
                .WaitAsync(TimeSpan.FromSeconds(5));
            Assert.False(timedOut.Ready);
            Assert.Equal("external_authority_timeout", timedOut.Code);
            Assert.Equal(1, provider.ValidationInvocationCount);
            Assert.Equal(1, provider.ReentrantValidationCallsInFlight);
            Assert.Equal("complete", provider.ReentrantReconciliationCode);
            Assert.Equal(1, first.ProviderCallDiagnostics.ValidationCallsInFlight);
            Assert.Equal(1, second.ProviderCallDiagnostics.ValidationCallsInFlight);
            Assert.Equal(1, second.ProviderCallDiagnostics.TotalCallsInFlight);

            byte[] retainedExternal = Assert.IsType<byte[]>(
                provider.LastExternalCheckpointReference);
            byte[] retainedHmac = Assert.IsType<byte[]>(provider.LastAuditHmacReference);
            byte[] retainedStateCheckpoint = Assert.IsType<byte[]>(
                provider.LastStateCheckpointReference);
            Assert.Contains(retainedExternal, value => value != 0);
            Assert.Contains(retainedHmac, value => value != 0);
            Assert.Contains(retainedStateCheckpoint, value => value != 0);

            for (int attempt = 0; attempt < 6; attempt++)
            {
                PlayAuthorizationPostgresReadiness retained = await readiness.CheckAsync();
                Assert.False(retained.Ready);
                Assert.Equal("checkpoint_provider_validation_in_flight", retained.Code);
                Assert.Equal(1, provider.ValidationInvocationCount);
            }

            IPlayAuthorizationPostgresRepository retainedRepository =
                _fixture.CreateRepository(
                    _fixture.AdminDataSource,
                    providerFactory: second);
            PlayAuthorizationPostgresMutationResult? replay =
                await retainedRepository.LookupIdempotencyReceiptAsync(replayRequest);
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable, replay?.Code);
            PlayAuthorizationPostgresMutationResult mutation =
                await retainedRepository.RedeemInviteAsync(mutationSeed.Redeem(
                    Durable(
                        "validation-single-flight-mutation",
                        "validation-single-flight-mutation-key",
                        "validation-single-flight-mutation-body",
                        mutationBody),
                    mutationSecret));
            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.AuthorityUnavailable, mutation.Code);
            Assert.Equal(1, provider.ValidationInvocationCount);
            Assert.Equal(1, providerFactory.ProviderCallDiagnostics.TotalCallsInFlight);
            Assert.Same(retainedExternal, provider.LastExternalCheckpointReference);
            Assert.Same(retainedHmac, provider.LastAuditHmacReference);
            Assert.Same(retainedStateCheckpoint, provider.LastStateCheckpointReference);

            await provider.ReleaseAsync();
            for (int attempt = 0;
                 attempt < 50 && providerFactory.ProviderCallDiagnostics.TotalCallsInFlight != 0;
                 attempt++)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(10));
            }

            Assert.Equal(0, providerFactory.ProviderCallDiagnostics.TotalCallsInFlight);
            Assert.All(retainedExternal, value => Assert.Equal((byte)0, value));
            Assert.All(retainedHmac, value => Assert.Equal((byte)0, value));
            Assert.All(retainedStateCheckpoint, value => Assert.Equal((byte)0, value));
            PlayAuthorizationPostgresReadiness recovered = await readiness.CheckAsync();
            Assert.True(recovered.Ready, recovered.Code);
            Assert.Equal(2, provider.ValidationInvocationCount);
            Assert.Equal(0, providerFactory.ProviderCallDiagnostics.TotalCallsInFlight);
        }
        finally
        {
            provider.Release();
            CryptographicOperations.ZeroMemory(replaySecret);
            CryptographicOperations.ZeroMemory(replayBody);
            CryptographicOperations.ZeroMemory(mutationSecret);
            CryptographicOperations.ZeroMemory(mutationBody);
        }
    }

    [Fact]
    public async Task PublicationAcknowledgementMayAliasOwnedRequestDigest()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        var provider = new AliasingCheckpointAuthority(_fixture.Authorities);
        PlayAuthorizationPostgresDormantFactory providerFactory =
            _fixture.CreateProviderFactory(provider).BindCheckpointReconciliation(
                _fixture.AdminDataSource,
                _fixture.Authorities,
                _fixture.PublicationPolicy,
                TimeProvider.System);
        try
        {
            IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
                _fixture.AdminDataSource,
                providerFactory: providerFactory);
            PlayAuthorizationPostgresMutationResult result = await repository.RedeemInviteAsync(
                seed.Redeem(
                    Durable(
                        "publication-alias",
                        "publication-alias-key",
                        "publication-alias-body",
                        body),
                    exchangeSecret));

            Assert.Equal(PlayAuthorizationPostgresOutcomeCode.Applied, result.Code);
            Assert.Equal(1, provider.PublishInvocationCount);
            byte[] aliasedDigest = Assert.IsType<byte[]>(provider.LastPublicationAliasedDigest);
            Assert.All(aliasedDigest, value => Assert.Equal((byte)0, value));
            Assert.Equal(0, providerFactory.ProviderCallDiagnostics.TotalCallsInFlight);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(exchangeSecret);
            CryptographicOperations.ZeroMemory(body);
        }
    }

    [Fact]
    public async Task BaselineAcknowledgementMayAliasOwnedRequestDigest()
    {
        string databaseName = $"play_baseline_alias_{Guid.NewGuid():N}";
        await using (NpgsqlConnection admin = await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand create = admin.CreateCommand())
        {
            create.CommandText = $"CREATE DATABASE \"{databaseName}\"";
            await create.ExecuteNonQueryAsync();
        }

        var builder = new NpgsqlConnectionStringBuilder(_fixture.ConnectionString)
        {
            Database = databaseName
        };
        try
        {
            using var authority = new EphemeralTestAuthorities();
            await using NpgsqlDataSource dataSource =
                NpgsqlDataSource.Create(builder.ConnectionString);
            await new PlayAuthorizationPostgresMigrator(dataSource).MigrateAsync();
            await using (NpgsqlConnection connection = await dataSource.OpenConnectionAsync())
            await using (NpgsqlCommand provision = connection.CreateCommand())
            {
                provision.CommandText = """
                    UPDATE play_auth.authority_state
                    SET epoch = 1, generation = 1,
                        external_checkpoint = @checkpoint,
                        audit_hmac_key_id = @key_id,
                        clock_high_water_utc = clock_timestamp(),
                        updated_at_utc = clock_timestamp()
                    WHERE singleton = true
                    """;
                provision.Parameters.AddWithValue(
                    "checkpoint",
                    NpgsqlDbType.Bytea,
                    authority.Checkpoint);
                provision.Parameters.AddWithValue("key_id", authority.KeyId);
                Assert.Equal(1, await provision.ExecuteNonQueryAsync());
            }

            var provider = new AliasingCheckpointAuthority(authority);
            var services = new ServiceCollection();
            services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(provider);
            using ServiceProvider serviceProvider = services.BuildServiceProvider();
            PlayAuthorizationPostgresDormantFactory providerFactory = serviceProvider
                .GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
            PlayAuthorizationPostgresDormantFactory reconciler =
                providerFactory.BindCheckpointReconciliation(
                    dataSource,
                    authority,
                    _fixture.PublicationPolicy,
                    TimeProvider.System);
            PlayAuthorizationCheckpointReconciliationResult result =
                await reconciler.ReconcileAsync(1);

            Assert.True(result.Complete, result.Code);
            Assert.Equal(1, provider.BaselineInvocationCount);
            byte[] aliasedDigest = Assert.IsType<byte[]>(provider.LastBaselineAliasedDigest);
            Assert.All(aliasedDigest, value => Assert.Equal((byte)0, value));
            Assert.Equal(0, reconciler.ProviderCallDiagnostics.TotalCallsInFlight);
        }
        finally
        {
            await using NpgsqlConnection admin = await _fixture.AdminDataSource.OpenConnectionAsync();
            await using NpgsqlCommand drop = admin.CreateCommand();
            drop.CommandText = $"DROP DATABASE IF EXISTS \"{databaseName}\" WITH (FORCE)";
            await drop.ExecuteNonQueryAsync();
        }
    }

    [Fact]
    public async Task ExpiredLeaseAllowsHigherFenceAndLateOldPublisherCannotFinalize()
    {
        SeededInvite seed = await _fixture.SeedInviteAsync();
        byte[] exchangeSecret = RandomNumberGenerator.GetBytes(48);
        byte[] body = Encoding.UTF8.GetBytes($"{{\"exchangeId\":\"{seed.ExchangeId}\"}}");
        var ignoring = new IgnoringCancellationCheckpointPublisher(
            _fixture.Authorities,
            TimeSpan.FromMilliseconds(40));
        var shortLeasePolicy = new PlayAuthorizationCheckpointPublicationPolicy(
            claimLease: TimeSpan.FromMilliseconds(750),
            databaseFinalizationDeadline: TimeSpan.FromMilliseconds(200),
            clockSkew: TimeSpan.FromMilliseconds(20));
        PlayAuthorizationPostgresDormantFactory firstReconciler =
            _fixture.CreateProviderFactory(ignoring).BindCheckpointReconciliation(
                _fixture.AdminDataSource,
                _fixture.Authorities,
                shortLeasePolicy,
                TimeProvider.System);
        IPlayAuthorizationPostgresRepository repository = _fixture.CreateRepository(
            _fixture.AdminDataSource,
            providerFactory: firstReconciler,
            publicationPolicy: shortLeasePolicy);
        PlayAuthorizationPostgresMutationResult result = await repository.RedeemInviteAsync(
            seed.Redeem(
                Durable("ignored-cancel", "ignored-cancel-key", "ignored-cancel-body", body),
                exchangeSecret));
        Assert.Equal(PlayAuthorizationPostgresOutcomeCode.CheckpointPending, result.Code);

        await using NpgsqlConnection connection = await _fixture.AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            SELECT state, lease_owner IS NOT NULL, fencing_token > 0
            FROM play_auth.checkpoint_publications AS publication
            JOIN play_auth.audit_log AS audit ON audit.sequence = publication.audit_sequence
            WHERE audit.aggregate_id = @id
            """;
        command.Parameters.AddWithValue("id", seed.InviteId);
        await using NpgsqlDataReader reader = await command.ExecuteReaderAsync();
        Assert.True(await reader.ReadAsync());
        Assert.Equal("pending", reader.GetString(0));
        Assert.True(reader.GetBoolean(1));
        Assert.True(reader.GetBoolean(2));

        await reader.DisposeAsync();
        await connection.DisposeAsync();
        await Task.Delay(shortLeasePolicy.ClaimLease + TimeSpan.FromMilliseconds(150));

        PlayAuthorizationPostgresDormantFactory higherFenceReconciler =
            _fixture.CreateProviderFactory(_fixture.Authorities)
                .BindCheckpointReconciliation(
                    _fixture.AdminDataSource,
                    _fixture.Authorities,
                    shortLeasePolicy,
                    TimeProvider.System);
        PlayAuthorizationCheckpointReconciliationResult recovered =
            await higherFenceReconciler.ReconcileAsync(1);
        Assert.True(recovered.Complete, recovered.Code);

        await ignoring.ReleaseAsync();
        Assert.NotNull(ignoring.LateAcknowledgement);
        Assert.Equal(
            PlayAuthorizationCheckpointPublicationDisposition.RejectedOutOfOrder,
            ignoring.LateAcknowledgement!.Disposition);
        Assert.Equal(1L, ignoring.LateAcknowledgement.AcceptedFencingToken);

        await using (NpgsqlConnection verify = await _fixture.AdminDataSource.OpenConnectionAsync())
        await using (NpgsqlCommand final = verify.CreateCommand())
        {
            final.CommandText = """
                SELECT publication.state, publication.fencing_token,
                       publication.attempt_count, publication.lease_owner IS NULL,
                       publication.lease_expires_at_utc IS NULL
                FROM play_auth.checkpoint_publications AS publication
                JOIN play_auth.audit_log AS audit ON audit.sequence = publication.audit_sequence
                WHERE audit.aggregate_id = @id
                """;
            final.Parameters.AddWithValue("id", seed.InviteId);
            await using NpgsqlDataReader finalReader = await final.ExecuteReaderAsync();
            Assert.True(await finalReader.ReadAsync());
            Assert.Equal("published", finalReader.GetString(0));
            Assert.Equal(2L, finalReader.GetInt64(1));
            Assert.Equal(2, finalReader.GetInt32(2));
            Assert.True(finalReader.GetBoolean(3));
            Assert.True(finalReader.GetBoolean(4));
        }

        CryptographicOperations.ZeroMemory(exchangeSecret);
        CryptographicOperations.ZeroMemory(body);
    }

    private static PlayAuthorizationDurableRequest Durable(
        string scope,
        string key,
        string fingerprintSource,
        byte[] body)
        => new(
            scope,
            key,
            Sha256(fingerprintSource),
            PlayAuthorizationReceiptEnvelope.Json(
                PlayAuthorizationReceiptKind.ExchangeIssued,
                201,
                body),
            PlayAuthorizationOperation.RedeemInvite);

    private static string Sha256(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static bool Contains(byte[] haystack, byte[] needle)
        => needle.Length > 0 && haystack.AsSpan().IndexOf(needle) >= 0;

    private static object ReadPrivate(object target, string fieldName)
        => target.GetType()
               .GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic)
               ?.GetValue(target)
           ?? throw new InvalidOperationException($"Missing private field {fieldName}.");
}

public sealed class PlayAuthorizationPostgresFixture : IAsyncLifetime
{
    private readonly string _root = Path.Combine(
        Path.GetTempPath(),
        $"chummer-play-postgres-{Guid.NewGuid():N}");
    private readonly PostgreSqlContainer _container;
    private IDataProtectionProvider? _dataProtection;

    public PlayAuthorizationPostgresFixture()
    {
        string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        _container = new PostgreSqlBuilder("postgres:17-alpine")
            .WithDatabase("chummer_play_auth")
            .WithUsername("postgres")
            .WithPassword(password)
            .Build();
        Authorities = new EphemeralTestAuthorities();
    }

    public NpgsqlDataSource AdminDataSource { get; private set; } = null!;
    public string ConnectionString => _container.GetConnectionString();
    public string DataProtectionPath => Path.Combine(_root, "keys");
    public EphemeralTestAuthorities Authorities { get; }
    public PlayAuthorizationCheckpointPublicationPolicy PublicationPolicy { get; } = new(
        claimLease: TimeSpan.FromSeconds(10),
        databaseFinalizationDeadline: TimeSpan.FromSeconds(2),
        clockSkew: TimeSpan.FromSeconds(1));
    public PlayAuthorizationReplaySafetyPolicy ReplaySafetyPolicy { get; } = new(
        maximumCapabilityOrReplayWindow: TimeSpan.FromDays(30),
        clockSkew: TimeSpan.FromMinutes(5));

    public async Task InitializeAsync()
    {
        Directory.CreateDirectory(DataProtectionPath);
        await _container.StartAsync();
        AdminDataSource = NpgsqlDataSource.Create(ConnectionString);
        var migrator = new PlayAuthorizationPostgresMigrator(AdminDataSource);
        await migrator.MigrateAsync();
        await using NpgsqlConnection connection = await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand provision = connection.CreateCommand();
        provision.CommandText = """
            UPDATE play_auth.authority_state
            SET epoch = 1,
                generation = 1,
                external_checkpoint = @checkpoint,
                audit_hmac_key_id = @key_id,
                clock_high_water_utc = clock_timestamp(),
                updated_at_utc = clock_timestamp()
            WHERE singleton = true
            """;
        provision.Parameters.AddWithValue("checkpoint", NpgsqlDbType.Bytea, Authorities.Checkpoint);
        provision.Parameters.AddWithValue("key_id", Authorities.KeyId);
        Assert.Equal(1, await provision.ExecuteNonQueryAsync());
        _dataProtection = CreateDataProtectionProvider();
    }

    public async Task DisposeAsync()
    {
        if (AdminDataSource is not null)
        {
            await AdminDataSource.DisposeAsync();
        }

        await _container.DisposeAsync();
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }

        Authorities.Dispose();
    }

    public IPlayAuthorizationPostgresRepository CreateRepository(
        NpgsqlDataSource dataSource,
        IPlayAuthorizationCommitObserver? observer = null,
        IPlayAuthorizationReceiptCipher? receiptCipher = null,
        IPlayAuthorizationHmacAuthority? hmacAuthority = null,
        IPlayAuthorizationCheckpointAuthority? checkpointAuthority = null,
        IPlayAuthorizationEpochAuthority? epochAuthority = null,
        PlayAuthorizationPostgresDormantFactory? providerFactory = null,
        PlayAuthorizationCheckpointPublicationPolicy? publicationPolicy = null,
        IPlayAuthorizationPostgresUnitOfWorkFactory? unitOfWorkFactory = null)
    {
        if (checkpointAuthority is not null && providerFactory is not null)
        {
            throw new InvalidOperationException(
                "Tests cannot mix a raw checkpoint authority with another dormant provider factory.");
        }

        PlayAuthorizationPostgresDormantFactory factory = providerFactory
            ?? CreateProviderFactory(checkpointAuthority ?? Authorities);
        return factory.CreateRepository(
            dataSource,
            unitOfWorkFactory ?? new NpgsqlPlayAuthorizationUnitOfWorkFactory(dataSource),
            epochAuthority ?? Authorities,
            hmacAuthority ?? Authorities,
            publicationPolicy ?? PublicationPolicy,
            receiptCipher ?? new DataProtectionPlayAuthorizationReceiptCipher(
                _dataProtection ?? throw new InvalidOperationException("Fixture is not initialized.")),
            observer ?? new NoOpPlayAuthorizationCommitObserver(),
            TimeProvider.System);
    }

    public IPlayAuthorizationCheckpointPublicationReconciler CreateReconciler(
        NpgsqlDataSource dataSource,
        IPlayAuthorizationCheckpointAuthority? checkpointAuthority = null)
        => CreateProviderFactory(checkpointAuthority ?? Authorities)
            .BindCheckpointReconciliation(
                dataSource,
                Authorities,
                PublicationPolicy,
                TimeProvider.System);

    public PlayAuthorizationPostgresDormantFactory CreateProviderFactory(
        IPlayAuthorizationCheckpointAuthority checkpointAuthority)
    {
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(
                checkpointAuthority);
        ServiceProvider serviceProvider = activation.BuildServiceProvider();
        return serviceProvider.GetRequiredService<
            PlayAuthorizationPostgresDormantFactory>();
    }

    public async Task<SeededInvite> SeedInviteAsync()
    {
        string suffix = Guid.NewGuid().ToString("N");
        string sessionId = $"session-{suffix}";
        string participantId = $"participant-{suffix}";
        string inviteId = $"invite-{suffix}";
        string exchangeId = $"exchange-{suffix}";
        string userId = $"user-{suffix}";
        byte[] inviteSecret = RandomNumberGenerator.GetBytes(48);
        PlayAuthorizationKeyedDigest verifier = await Authorities.ComputeCapabilityAsync(
            PlayAuthorizationCapabilityKind.Invite,
            inviteId,
            inviteSecret,
            requiredKeyId: null,
            CancellationToken.None);
        DateTimeOffset now = DateTimeOffset.UtcNow;
        await using NpgsqlConnection connection = await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlTransaction transaction = await connection.BeginTransactionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO play_auth.sessions(
                session_id, campaign_id, run_id, group_id, status, authorization_version,
                epoch, generation, created_by_user_id, created_at_utc, updated_at_utc)
            VALUES (@session, @campaign, @run, @group, 'active', 1, 1, 1,
                    'seed-admin', @now, @now);

            INSERT INTO play_auth.participants(
                participant_id, session_id, user_id, role, source_kind, source_id,
                status, authorization_version, epoch, generation, added_by_user_id,
                created_at_utc, updated_at_utc)
            VALUES (@participant, @session, @user, 'player', 'explicit_participant',
                    @participant, 'active', 1, 1, 1, 'seed-admin', @now, @now);

            INSERT INTO play_auth.invites(
                invite_id, session_id, participant_id, target_user_id, requested_role,
                status, session_authorization_version, participant_authorization_version,
                epoch, generation, created_by_user_id, created_at_utc, updated_at_utc,
                expires_at_utc)
            VALUES (@invite, @session, @participant, @user, 'player', 'pending',
                    1, 1, 1, 1, 'seed-admin', @now, @now, @expires);

            INSERT INTO play_auth.capability_verifiers(
                capability_kind, capability_id, epoch, generation, key_id,
                verifier_hmac, created_at_utc, expires_at_utc)
            VALUES ('invite', @invite, 1, 1, @key_id, @verifier, @now, @expires)
            """;
        command.Parameters.AddWithValue("session", sessionId);
        command.Parameters.AddWithValue("campaign", $"campaign-{suffix}");
        command.Parameters.AddWithValue("run", $"run-{suffix}");
        command.Parameters.AddWithValue("group", $"group-{suffix}");
        command.Parameters.AddWithValue("participant", participantId);
        command.Parameters.AddWithValue("user", userId);
        command.Parameters.AddWithValue("invite", inviteId);
        command.Parameters.AddWithValue("now", now);
        command.Parameters.AddWithValue("expires", now.AddMinutes(15));
        command.Parameters.AddWithValue("key_id", verifier.KeyId);
        command.Parameters.AddWithValue("verifier", NpgsqlDbType.Bytea, verifier.Digest);
        await command.ExecuteNonQueryAsync();
        await transaction.CommitAsync();
        CryptographicOperations.ZeroMemory(verifier.Digest);
        return new SeededInvite(
            sessionId,
            participantId,
            inviteId,
            exchangeId,
            userId,
            inviteSecret,
            now);
    }

    public async Task<int> CountAsync(string sql, string id)
    {
        await using NpgsqlConnection connection = await AdminDataSource.OpenConnectionAsync();
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = sql;
        command.Parameters.AddWithValue("id", id);
        return Convert.ToInt32(await command.ExecuteScalarAsync());
    }

    private IDataProtectionProvider CreateDataProtectionProvider()
        => DataProtectionProvider.Create(
            new DirectoryInfo(DataProtectionPath),
            configuration => configuration.SetApplicationName("Chummer.PlayAuthorization.Postgres.Tests"));
}

public sealed record SeededInvite(
    string SessionId,
    string ParticipantId,
    string InviteId,
    string ExchangeId,
    string UserId,
    byte[] InviteSecret,
    DateTimeOffset CreatedAtUtc)
{
    public PlayAuthorizationRedeemMutation Redeem(
        PlayAuthorizationDurableRequest durable,
        byte[] exchangeSecret)
        => new(
            durable,
            InviteId,
            ExchangeId,
            SessionId,
            ParticipantId,
            UserId,
            "player",
            InviteSecret,
            exchangeSecret,
            new string('d', 64),
            1,
            1,
            DateTimeOffset.UtcNow.AddMinutes(5),
            Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes("test-actor"))).ToLowerInvariant());
}

public sealed class EphemeralTestAuthorities :
    IPlayAuthorizationEpochAuthority,
    IPlayAuthorizationHmacAuthority,
    IPlayAuthorizationCheckpointAuthority,
    IDisposable
{
    private readonly byte[] _key = RandomNumberGenerator.GetBytes(32);
    private readonly object _publicationGate = new();
    private readonly Dictionary<Guid, PublishedCheckpoint> _published = new();
    private readonly Dictionary<Guid, byte[]> _verifiedBaselines = new();
    private long _publishedSequence;

    public string KeyId { get; } = $"ephemeral-{Guid.NewGuid():N}";
    public byte[] Checkpoint { get; } = RandomNumberGenerator.GetBytes(32);
    public PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; } = new(
        TimeSpan.FromSeconds(2),
        SupportsMonotonicFencing: true,
        PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
        PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
        PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
        PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes);

    public ValueTask<PlayAuthorizationExternalEpoch> ReadCurrentAsync(CancellationToken cancellationToken)
        => ValueTask.FromResult(new PlayAuthorizationExternalEpoch(1, 1, Checkpoint.ToArray()));

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
        PlayAuthorizationCapabilityKind kind,
        string capabilityId,
        ReadOnlyMemory<byte> secret,
        string? requiredKeyId,
        CancellationToken cancellationToken)
    {
        if (requiredKeyId is not null && !string.Equals(requiredKeyId, KeyId, StringComparison.Ordinal))
        {
            throw new PlayAuthorizationExternalAuthorityUnavailableException("HMAC key");
        }

        using var hmac = new HMACSHA256(_key);
        byte[] prefix = Encoding.UTF8.GetBytes($"capability\0{kind.ToDatabaseValue()}\0{capabilityId}\0");
        byte[] input = new byte[prefix.Length + secret.Length];
        prefix.CopyTo(input, 0);
        secret.Span.CopyTo(input.AsSpan(prefix.Length));
        try
        {
            return ValueTask.FromResult(new PlayAuthorizationKeyedDigest(KeyId, hmac.ComputeHash(input)));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(prefix);
            CryptographicOperations.ZeroMemory(input);
        }
    }

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
        PlayAuthorizationAuditDigestInput input,
        CancellationToken cancellationToken)
    {
        using var hmac = new HMACSHA256(_key);
        byte[] header = Encoding.UTF8.GetBytes($"audit\0{input.Epoch}\0{input.Generation}\0{input.Sequence}\0");
        byte[] bytes = new byte[header.Length + input.PreviousHmac.Length + input.PayloadSha256.Length];
        header.CopyTo(bytes, 0);
        input.PreviousHmac.CopyTo(bytes, header.Length);
        input.PayloadSha256.CopyTo(bytes, header.Length + input.PreviousHmac.Length);
        try
        {
            return ValueTask.FromResult(new PlayAuthorizationKeyedDigest(KeyId, hmac.ComputeHash(bytes)));
        }
        finally
        {
            CryptographicOperations.ZeroMemory(header);
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
    {
        if (externalEpoch.Epoch != 1
            || externalEpoch.Generation != 1
            || databaseState.Epoch != 1
            || databaseState.Generation != 1
            || !CryptographicOperations.FixedTimeEquals(Checkpoint, externalEpoch.Checkpoint)
            || !CryptographicOperations.FixedTimeEquals(Checkpoint, databaseState.ExternalCheckpoint))
        {
            throw new PlayAuthorizationExternalAuthorityUnavailableException("checkpoint");
        }

        return ValueTask.CompletedTask;
    }

    public async ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        await ValidateAsync(externalEpoch, verification.State, cancellationToken);
        byte[] canonical = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
            verification.BaselineId,
            verification.State,
            verification.DigestAlgorithm,
            verification.CanonicalVersion);
        bool accepted = CryptographicOperations.FixedTimeEquals(
            canonical,
            verification.PayloadDigestSha256);
        lock (_publicationGate)
        {
            if (accepted)
            {
                if (_verifiedBaselines.TryGetValue(
                        verification.BaselineId,
                        out byte[]? previous))
                {
                    CryptographicOperations.ZeroMemory(previous);
                }

                _verifiedBaselines[verification.BaselineId] = canonical.ToArray();
                _publishedSequence = Math.Max(
                    _publishedSequence,
                    verification.State.AuditHeadSequence);
            }
        }

        CryptographicOperations.ZeroMemory(canonical);
        return new PlayAuthorizationCheckpointBaselineAcknowledgement(
            accepted,
            verification.BaselineId,
            verification.PayloadDigestSha256.ToArray());
    }

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        byte[] canonical = PlayAuthorizationCheckpointCanonicalizer.ComputePayloadDigest(
            envelope.PublicationId,
            envelope.State,
            envelope.DigestAlgorithm,
            envelope.CanonicalVersion);
        bool canonicalPayload = CryptographicOperations.FixedTimeEquals(
            canonical,
            envelope.PayloadDigestSha256);
        CryptographicOperations.ZeroMemory(canonical);
        PlayAuthorizationCheckpointPublicationDisposition disposition;
        lock (_publicationGate)
        {
            if (!canonicalPayload
                || envelope.State.Epoch != 1
                || envelope.State.Generation != 1
                || envelope.FencingToken <= 0
                || !CryptographicOperations.FixedTimeEquals(
                    envelope.State.ExternalCheckpoint,
                    Checkpoint))
            {
                disposition = PlayAuthorizationCheckpointPublicationDisposition.RejectedAuthority;
            }
            else if (_published.TryGetValue(envelope.PublicationId, out PublishedCheckpoint? existing))
            {
                bool samePayload = CryptographicOperations.FixedTimeEquals(
                    existing.PayloadDigestSha256,
                    envelope.PayloadDigestSha256);
                if (!samePayload
                    || existing.Sequence != envelope.State.AuditHeadSequence
                    || envelope.FencingToken < existing.MaximumFencingToken)
                {
                    disposition = PlayAuthorizationCheckpointPublicationDisposition.RejectedOutOfOrder;
                }
                else
                {
                    existing.MaximumFencingToken = envelope.FencingToken;
                    disposition = PlayAuthorizationCheckpointPublicationDisposition.AlreadyPublished;
                }
            }
            else if (envelope.State.AuditHeadSequence == _publishedSequence + 1)
            {
                _published[envelope.PublicationId] = new PublishedCheckpoint(
                    envelope.State.AuditHeadSequence,
                    envelope.PayloadDigestSha256.ToArray(),
                    envelope.FencingToken);
                _publishedSequence = envelope.State.AuditHeadSequence;
                disposition = PlayAuthorizationCheckpointPublicationDisposition.Accepted;
            }
            else
            {
                disposition = PlayAuthorizationCheckpointPublicationDisposition.RejectedOutOfOrder;
            }
        }

        return ValueTask.FromResult(new PlayAuthorizationCheckpointPublicationAcknowledgement(
            disposition,
            envelope.PublicationId,
            envelope.FencingToken,
            envelope.PayloadDigestSha256.ToArray()));
    }

    public void Dispose()
    {
        CryptographicOperations.ZeroMemory(_key);
        CryptographicOperations.ZeroMemory(Checkpoint);
        foreach (PublishedCheckpoint checkpoint in _published.Values)
        {
            CryptographicOperations.ZeroMemory(checkpoint.PayloadDigestSha256);
        }

        foreach (byte[] digest in _verifiedBaselines.Values)
        {
            CryptographicOperations.ZeroMemory(digest);
        }
    }

    private sealed class PublishedCheckpoint
    {
        public PublishedCheckpoint(long sequence, byte[] payloadDigestSha256, long maximumFencingToken)
        {
            Sequence = sequence;
            PayloadDigestSha256 = payloadDigestSha256;
            MaximumFencingToken = maximumFencingToken;
        }

        public long Sequence { get; }
        public byte[] PayloadDigestSha256 { get; }
        public long MaximumFencingToken { get; set; }
    }
}

public sealed class OpenGenericCheckpointAuthority<T> :
    IPlayAuthorizationCheckpointAuthority
{
    public PlayAuthorizationCheckpointProviderCapabilities Capabilities =>
        throw DormantAlias();

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => throw DormantAlias();

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => throw DormantAlias();

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => throw DormantAlias();

    private static NotSupportedException DormantAlias() => new(
        "Open generic checkpoint aliases are registration-validation fixtures only.");
}

public sealed class CheckpointAuthorityPropertyWrapper
{
    public CheckpointAuthorityPropertyWrapper(
        IPlayAuthorizationCheckpointAuthority authority)
    {
        Authority = authority;
    }

    public IPlayAuthorizationCheckpointAuthority Authority { get; }
}

public sealed class DisposalTrackingCheckpointAuthority :
    IPlayAuthorizationCheckpointAuthority,
    IDisposable,
    IAsyncDisposable
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;
    private int _disposeCount;
    private int _disposeAsyncCount;

    public DisposalTrackingCheckpointAuthority(
        IPlayAuthorizationCheckpointAuthority inner)
    {
        _inner = inner;
    }

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities =>
        _inner.Capabilities;
    public int DisposeCount => Volatile.Read(ref _disposeCount);
    public int DisposeAsyncCount => Volatile.Read(ref _disposeAsyncCount);

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => _inner.ValidateAsync(externalEpoch, databaseState, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => _inner.VerifyBaselineAsync(verification, externalEpoch, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => _inner.PublishAsync(envelope, cancellationToken);

    public void Dispose() => Interlocked.Increment(ref _disposeCount);

    public ValueTask DisposeAsync()
    {
        Interlocked.Increment(ref _disposeAsyncCount);
        return ValueTask.CompletedTask;
    }
}

public sealed class FailAuditOnceAuthority : IPlayAuthorizationHmacAuthority
{
    private readonly IPlayAuthorizationHmacAuthority _inner;
    private int _remaining = 1;

    public FailAuditOnceAuthority(IPlayAuthorizationHmacAuthority inner) => _inner = inner;

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
        PlayAuthorizationCapabilityKind kind,
        string capabilityId,
        ReadOnlyMemory<byte> secret,
        string? requiredKeyId,
        CancellationToken cancellationToken)
        => _inner.ComputeCapabilityAsync(kind, capabilityId, secret, requiredKeyId, cancellationToken);

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
        PlayAuthorizationAuditDigestInput input,
        CancellationToken cancellationToken)
        => Interlocked.Exchange(ref _remaining, 0) == 1
            ? ValueTask.FromException<PlayAuthorizationKeyedDigest>(
                new PlayAuthorizationExternalAuthorityUnavailableException("test audit"))
            : _inner.ComputeAuditAsync(input, cancellationToken);
}

public sealed class CommitThenThrowOnceUnitOfWorkFactory : IPlayAuthorizationPostgresUnitOfWorkFactory
{
    private readonly IPlayAuthorizationPostgresUnitOfWorkFactory _inner;
    private int _remaining = 1;
    private int _beginCount;

    public CommitThenThrowOnceUnitOfWorkFactory(IPlayAuthorizationPostgresUnitOfWorkFactory inner)
        => _inner = inner;

    public int BeginCount => Volatile.Read(ref _beginCount);
    public string FailureMessage { get; } = "simulated connection loss after durable commit";

    public async ValueTask<IPlayAuthorizationPostgresUnitOfWork> BeginAsync(
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _beginCount);
        return new CommitThenThrowOnceUnitOfWork(
            await _inner.BeginAsync(cancellationToken),
            this);
    }

    private bool TakeFailure() => Interlocked.Exchange(ref _remaining, 0) == 1;

    private sealed class CommitThenThrowOnceUnitOfWork : IPlayAuthorizationPostgresUnitOfWork
    {
        private readonly IPlayAuthorizationPostgresUnitOfWork _inner;
        private readonly CommitThenThrowOnceUnitOfWorkFactory _owner;

        public CommitThenThrowOnceUnitOfWork(
            IPlayAuthorizationPostgresUnitOfWork inner,
            CommitThenThrowOnceUnitOfWorkFactory owner)
        {
            _inner = inner;
            _owner = owner;
        }

        public NpgsqlConnection Connection => _inner.Connection;
        public NpgsqlTransaction Transaction => _inner.Transaction;

        public async Task CommitAsync(CancellationToken cancellationToken)
        {
            await _inner.CommitAsync(cancellationToken);
            if (_owner.TakeFailure())
            {
                throw new IOException(_owner.FailureMessage);
            }
        }

        public Task RollbackAsync(CancellationToken cancellationToken)
            => _inner.RollbackAsync(cancellationToken);

        public ValueTask DisposeAsync() => _inner.DisposeAsync();
    }
}

public sealed class CountingUnitOfWorkFactory : IPlayAuthorizationPostgresUnitOfWorkFactory
{
    private readonly IPlayAuthorizationPostgresUnitOfWorkFactory _inner;
    private int _beginCount;

    public CountingUnitOfWorkFactory(IPlayAuthorizationPostgresUnitOfWorkFactory inner)
        => _inner = inner;

    public int BeginCount => Volatile.Read(ref _beginCount);

    public ValueTask<IPlayAuthorizationPostgresUnitOfWork> BeginAsync(
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _beginCount);
        return _inner.BeginAsync(cancellationToken);
    }
}

public sealed class SixtyFourByteHmacAuthority : IPlayAuthorizationHmacAuthority
{
    private readonly IPlayAuthorizationHmacAuthority _inner;
    private readonly bool _malformedAudit;

    public SixtyFourByteHmacAuthority(
        IPlayAuthorizationHmacAuthority inner,
        bool malformedAudit)
    {
        _inner = inner;
        _malformedAudit = malformedAudit;
    }

    public async ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
        PlayAuthorizationCapabilityKind kind,
        string capabilityId,
        ReadOnlyMemory<byte> secret,
        string? requiredKeyId,
        CancellationToken cancellationToken)
    {
        PlayAuthorizationKeyedDigest valid = await _inner.ComputeCapabilityAsync(
            kind,
            capabilityId,
            secret,
            requiredKeyId,
            cancellationToken);
        return _malformedAudit ? valid : Expand(valid);
    }

    public async ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
        PlayAuthorizationAuditDigestInput input,
        CancellationToken cancellationToken)
    {
        PlayAuthorizationKeyedDigest valid = await _inner.ComputeAuditAsync(input, cancellationToken);
        return _malformedAudit ? Expand(valid) : valid;
    }

    private static PlayAuthorizationKeyedDigest Expand(PlayAuthorizationKeyedDigest valid)
    {
        byte[] malformed = new byte[64];
        valid.Digest.CopyTo(malformed, 0);
        valid.Digest.CopyTo(malformed, valid.Digest.Length);
        CryptographicOperations.ZeroMemory(valid.Digest);
        return new PlayAuthorizationKeyedDigest(valid.KeyId, malformed);
    }
}

public sealed class CancelRequestAfterCommitObserver : IPlayAuthorizationCommitObserver
{
    private readonly CancellationTokenSource _requestCancellation;

    public CancelRequestAfterCommitObserver(CancellationTokenSource requestCancellation)
        => _requestCancellation = requestCancellation;

    public ValueTask AfterCommitAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        _requestCancellation.Cancel();
        return ValueTask.CompletedTask;
    }
}

public sealed class AlwaysUnavailableCheckpointPublisher : IPlayAuthorizationCheckpointAuthority
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;

    public AlwaysUnavailableCheckpointPublisher(IPlayAuthorizationCheckpointAuthority inner)
        => _inner = inner;

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities => _inner.Capabilities;

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => _inner.ValidateAsync(externalEpoch, databaseState, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => _inner.VerifyBaselineAsync(verification, externalEpoch, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => ValueTask.FromException<PlayAuthorizationCheckpointPublicationAcknowledgement>(
            new PlayAuthorizationExternalAuthorityUnavailableException("test publish"));
}

public sealed class CheckpointCapabilityOverrideAuthority : IPlayAuthorizationCheckpointAuthority
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;

    public CheckpointCapabilityOverrideAuthority(
        IPlayAuthorizationCheckpointAuthority inner,
        PlayAuthorizationCheckpointProviderCapabilities capabilities)
    {
        _inner = inner;
        Capabilities = capabilities;
    }

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; }

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => _inner.ValidateAsync(externalEpoch, databaseState, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => _inner.VerifyBaselineAsync(verification, externalEpoch, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => _inner.PublishAsync(envelope, cancellationToken);
}

public sealed class RejectOutOfOrderCheckpointPublisher : IPlayAuthorizationCheckpointAuthority
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;

    public RejectOutOfOrderCheckpointPublisher(IPlayAuthorizationCheckpointAuthority inner)
        => _inner = inner;

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities => _inner.Capabilities;

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => _inner.ValidateAsync(externalEpoch, databaseState, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => _inner.VerifyBaselineAsync(verification, externalEpoch, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => ValueTask.FromResult(new PlayAuthorizationCheckpointPublicationAcknowledgement(
            PlayAuthorizationCheckpointPublicationDisposition.RejectedOutOfOrder,
            envelope.PublicationId,
            envelope.FencingToken,
            envelope.PayloadDigestSha256.ToArray()));
}

public sealed class FixedEpochAuthority : IPlayAuthorizationEpochAuthority
{
    private readonly PlayAuthorizationExternalEpoch _epoch;

    public FixedEpochAuthority(PlayAuthorizationExternalEpoch epoch) => _epoch = epoch;

    public ValueTask<PlayAuthorizationExternalEpoch> ReadCurrentAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        return ValueTask.FromResult(_epoch with { Checkpoint = _epoch.Checkpoint.ToArray() });
    }
}

public sealed class RotateAuthorityDuringAuditAuthority : IPlayAuthorizationHmacAuthority
{
    private readonly IPlayAuthorizationHmacAuthority _inner;
    private readonly NpgsqlDataSource _dataSource;
    private int _remaining = 1;

    public RotateAuthorityDuringAuditAuthority(
        IPlayAuthorizationHmacAuthority inner,
        NpgsqlDataSource dataSource)
    {
        _inner = inner;
        _dataSource = dataSource;
    }

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
        PlayAuthorizationCapabilityKind kind,
        string capabilityId,
        ReadOnlyMemory<byte> secret,
        string? requiredKeyId,
        CancellationToken cancellationToken)
        => _inner.ComputeCapabilityAsync(kind, capabilityId, secret, requiredKeyId, cancellationToken);

    public async ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
        PlayAuthorizationAuditDigestInput input,
        CancellationToken cancellationToken)
    {
        PlayAuthorizationKeyedDigest digest =
            await _inner.ComputeAuditAsync(input, cancellationToken);
        if (Interlocked.Exchange(ref _remaining, 0) == 1)
        {
            await SetEpochAsync(2, 1, cancellationToken);
        }

        return digest;
    }

    public Task RestoreAsync() => SetEpochAsync(1, 1, CancellationToken.None);

    private async Task SetEpochAsync(long epoch, long generation, CancellationToken cancellationToken)
    {
        await using NpgsqlConnection connection = await _dataSource.OpenConnectionAsync(cancellationToken);
        await using NpgsqlCommand command = connection.CreateCommand();
        command.CommandText = """
            UPDATE play_auth.authority_state
            SET epoch = @epoch, generation = @generation
            WHERE singleton = true
            """;
        command.Parameters.AddWithValue("epoch", epoch);
        command.Parameters.AddWithValue("generation", generation);
        Assert.Equal(1, await command.ExecuteNonQueryAsync(cancellationToken));
    }
}

public sealed class AliasingCheckpointAuthority : IPlayAuthorizationCheckpointAuthority
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;
    private int _baselineInvocationCount;
    private int _publishInvocationCount;

    public AliasingCheckpointAuthority(IPlayAuthorizationCheckpointAuthority inner)
        => _inner = inner;

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities => _inner.Capabilities;
    public int BaselineInvocationCount => Volatile.Read(ref _baselineInvocationCount);
    public int PublishInvocationCount => Volatile.Read(ref _publishInvocationCount);
    public byte[]? LastBaselineAliasedDigest { get; private set; }
    public byte[]? LastPublicationAliasedDigest { get; private set; }

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => _inner.ValidateAsync(externalEpoch, databaseState, cancellationToken);

    public async ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _baselineInvocationCount);
        PlayAuthorizationCheckpointBaselineAcknowledgement acknowledgement =
            await _inner.VerifyBaselineAsync(
                verification,
                externalEpoch,
                cancellationToken);
        try
        {
            LastBaselineAliasedDigest = verification.PayloadDigestSha256;
            return new(
                acknowledgement.Accepted,
                acknowledgement.BaselineId,
                verification.PayloadDigestSha256);
        }
        finally
        {
            if (!ReferenceEquals(
                    acknowledgement.PayloadDigestSha256,
                    verification.PayloadDigestSha256))
            {
                CryptographicOperations.ZeroMemory(acknowledgement.PayloadDigestSha256);
            }
        }
    }

    public async ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _publishInvocationCount);
        PlayAuthorizationCheckpointPublicationAcknowledgement acknowledgement =
            await _inner.PublishAsync(envelope, cancellationToken);
        try
        {
            LastPublicationAliasedDigest = envelope.PayloadDigestSha256;
            return new(
                acknowledgement.Disposition,
                acknowledgement.PublicationId,
                acknowledgement.AcceptedFencingToken,
                envelope.PayloadDigestSha256);
        }
        finally
        {
            if (!ReferenceEquals(
                    acknowledgement.PayloadDigestSha256,
                    envelope.PayloadDigestSha256))
            {
                CryptographicOperations.ZeroMemory(acknowledgement.PayloadDigestSha256);
            }
        }
    }
}

public sealed class SynchronouslyBlockingCheckpointValidationAuthority :
    IPlayAuthorizationCheckpointAuthority
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;
    private readonly TimeSpan _hardDeadline;
    private readonly TaskCompletionSource<bool> _release = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource<bool> _completed = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private int _validationInvocationCount;

    public SynchronouslyBlockingCheckpointValidationAuthority(
        IPlayAuthorizationCheckpointAuthority inner,
        TimeSpan hardDeadline)
    {
        _inner = inner;
        _hardDeadline = hardDeadline;
    }

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities =>
        _inner.Capabilities with { HardDeadline = _hardDeadline };
    public int ValidationInvocationCount => Volatile.Read(ref _validationInvocationCount);
    public Action? SynchronousPrefix { get; set; }
    public int ReentrantValidationCallsInFlight { get; set; }
    public string? ReentrantReconciliationCode { get; set; }
    public byte[]? LastExternalCheckpointReference { get; private set; }
    public byte[]? LastAuditHmacReference { get; private set; }
    public byte[]? LastStateCheckpointReference { get; private set; }

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _validationInvocationCount);
        LastExternalCheckpointReference = externalEpoch.Checkpoint;
        LastAuditHmacReference = databaseState.AuditHeadHmac;
        LastStateCheckpointReference = databaseState.ExternalCheckpoint;
        SynchronousPrefix?.Invoke();
        _release.Task.GetAwaiter().GetResult();
        return CompleteValidationAsync(externalEpoch, databaseState);
    }

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => _inner.VerifyBaselineAsync(verification, externalEpoch, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => _inner.PublishAsync(envelope, cancellationToken);

    public async Task ReleaseAsync()
    {
        Release();
        await _completed.Task;
    }

    public void Release() => _release.TrySetResult(true);

    private async ValueTask CompleteValidationAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState)
    {
        try
        {
            await _inner.ValidateAsync(
                externalEpoch,
                databaseState,
                CancellationToken.None);
        }
        finally
        {
            _completed.TrySetResult(true);
        }
    }
}

public sealed class IgnoringCancellationCheckpointPublisher : IPlayAuthorizationCheckpointAuthority
{
    private readonly IPlayAuthorizationCheckpointAuthority _inner;
    private readonly TaskCompletionSource<bool> _release = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource<bool> _completed = new(
        TaskCreationOptions.RunContinuationsAsynchronously);

    private readonly TimeSpan _hardDeadline;
    private int _publishInvocationCount;

    public IgnoringCancellationCheckpointPublisher(
        IPlayAuthorizationCheckpointAuthority inner,
        TimeSpan? hardDeadline = null)
    {
        _inner = inner;
        _hardDeadline = hardDeadline ?? TimeSpan.FromMilliseconds(100);
    }

    public PlayAuthorizationCheckpointPublicationAcknowledgement? LateAcknowledgement { get; private set; }
    public int PublishInvocationCount => Volatile.Read(ref _publishInvocationCount);

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities =>
        _inner.Capabilities with { HardDeadline = _hardDeadline };

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => _inner.ValidateAsync(externalEpoch, databaseState, cancellationToken);

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => _inner.VerifyBaselineAsync(verification, externalEpoch, cancellationToken);

    public async ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _publishInvocationCount);
        try
        {
            await _release.Task;
            PlayAuthorizationCheckpointPublicationAcknowledgement acknowledgement =
                await _inner.PublishAsync(envelope, CancellationToken.None);
            LateAcknowledgement = acknowledgement;
            return acknowledgement;
        }
        finally
        {
            _completed.TrySetResult(true);
        }
    }

    public async Task ReleaseAsync()
    {
        _release.TrySetResult(true);
        await _completed.Task;
    }
}
