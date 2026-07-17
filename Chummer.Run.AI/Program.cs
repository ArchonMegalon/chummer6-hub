using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Booster;
using Chummer.Run.AI.Services.Creative;
using Chummer.Run.AI.Services.Lore;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Observation;
using Chummer.Run.AI.Services.Interop;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.AI.Services.Transcription;
using Chummer.Run.AI.Services.Newspaper;
using Chummer.Run.AI.Security;
using CanonicalTranscriptionProvider = Chummer.Run.Contracts.Transcription.ITranscriptionProvider;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.

builder.Services.AddControllers();
builder.Services.AddSingleton<IProviderRouter, ProviderRouter>();
builder.Services.AddSingleton<IProviderAdapter>(sp =>
{
    var configuration = sp.GetRequiredService<IConfiguration>();
    var section = ResolveProviderSection(configuration);
    return new MockProviderAdapter(AiProvider.AiMagicx, section.GetValue<bool?>("AiMagicx:Enabled") ?? true, true);
});
builder.Services.AddSingleton<IProviderAdapter>(sp =>
{
    var configuration = sp.GetRequiredService<IConfiguration>();
    var section = ResolveProviderSection(configuration);
    return new MockProviderAdapter(AiProvider.OneMinAi, section.GetValue<bool?>("OneMinAi:Enabled") ?? true, true);
});
builder.Services.AddSingleton<IProviderAdapter>(sp =>
{
    var configuration = sp.GetRequiredService<IConfiguration>();
    var section = ResolveProviderSection(configuration);
    return new MockProviderAdapter(AiProvider.ChatPlayground, section.GetValue<bool?>("ChatPlayground:Enabled") ?? false, false);
});
builder.Services.AddSingleton<IProviderAdapter>(sp =>
{
    var configuration = sp.GetRequiredService<IConfiguration>();
    var section = ResolveProviderSection(configuration);
    return new MockProviderAdapter(AiProvider.PromptingSystems, section.GetValue<bool?>("PromptingSystems:Enabled") ?? false, false);
});
builder.Services.AddSingleton<IProviderAdapter, BrowserActGatewayAdapter>();
builder.Services.AddSingleton<IProviderAdapter, MarkupGoGatewayAdapter>();
builder.Services.AddSingleton<IProviderAdapter, PeekShotGatewayAdapter>();
builder.Services.AddSingleton<IPromptRegistry, PromptRegistry>();
builder.Services.AddSingleton<IAiGatewayService, AiGatewayService>();
builder.Services.AddSingleton<IAiBudgetService, AiBudgetService>();
builder.Services.AddSingleton<BoosterReceiptVerifier>();
builder.Services.AddSingleton<BoosterProjectionAccessGuard>();
builder.Services.AddSingleton<BoosterReceiptProjectionService>();
builder.Services.AddSingleton<ISkillToolAdapter, SessionProjectionSkillToolAdapter>();
builder.Services.AddSingleton<ISkillToolAdapter, LoreSearchSkillToolAdapter>();
builder.Services.AddSingleton<IGovernedSkillRuntimeService, GovernedSkillRuntimeService>();
builder.Services.AddSingleton<IConversationStore, ConversationStore>();
builder.Services.AddSingleton<IEvaluationStore, EvaluationStore>();
builder.Services.AddSingleton<IAssetLifecycleService, AssetLifecycleService>();
builder.Services.AddSingleton<IMediaRenderJobService, MediaRenderJobService>();
builder.Services.AddSingleton<IPortraitForgeService, PortraitForgeService>();
builder.Services.AddSingleton<IPacketFactoryService, PacketFactoryService>();
builder.Services.AddSingleton<INewsNetworkService, NewsNetworkService>();
builder.Services.AddSingleton<IRouteCinemaService, RouteCinemaService>();
builder.Services.AddSingleton<IShadowfeedService, ShadowfeedService>();
builder.Services.AddSingleton<INpcMessageVideoService, NpcMessageVideoService>();
builder.Services.AddSingleton<ISessionLedgerService, SessionLedgerService>();
builder.Services.AddSingleton<ISessionMemoryService, SessionMemoryService>();
builder.Services.AddSingleton<ISessionMemoryIngestionService, SessionMemoryIngestionService>();
builder.Services.AddSingleton<ISessionRuntimeBundleService, SessionRuntimeBundleService>();
builder.Services.AddSingleton<IOfflineSyncService, OfflineSyncService>();
builder.Services.AddSingleton<IGmOpsBoardService, GmOpsBoardService>();
builder.Services.AddHttpClient<IHubCrashAutomationClient, HubCrashAutomationClient>(client =>
{
    client.BaseAddress = ResolveHubApiBaseAddress(builder.Configuration);
    client.Timeout = TimeSpan.FromSeconds(20);
    string? token = builder.Configuration["FLEET_INTERNAL_API_TOKEN"];
    if (!string.IsNullOrWhiteSpace(token))
    {
        client.DefaultRequestHeaders.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", token.Trim());
    }
});
builder.Services.AddSingleton<IInteropExportService, InteropExportService>();
builder.Services.AddSingleton<IFastSignalDetector, FastSignalDetector>();
builder.Services.AddSingleton<ISpiderDeepIngestionService, SpiderDeepIngestionService>();
builder.Services.AddSingleton<IDirectorPolicyEngine, DirectorPolicyEngine>();
builder.Services.AddSingleton<IInterruptionBudgetService, InterruptionBudgetService>();
builder.Services.AddSingleton<IDeliveryOutboxService, DeliveryOutboxService>();
builder.Services.AddSingleton<ISpiderCardActionService, SpiderCardActionService>();
builder.Services.AddSingleton<LoreService>();
builder.Services.AddSingleton<ILoreService>(sp => sp.GetRequiredService<LoreService>());
builder.Services.AddSingleton<IPersonaMemoryService>(sp => sp.GetRequiredService<LoreService>());
builder.Services.AddSingleton<INewspaperValidationService, NewspaperValidationService>();
builder.Services.AddSingleton<INewspaperCompositionService, NewspaperCompositionService>();
builder.Services.AddSingleton<INewspaperHtmlRenderer, NewspaperHtmlRenderer>();
builder.Services.AddSingleton<INewspaperRenderService, NewspaperRenderService>();
builder.Services.AddSingleton<CanonicalTranscriptionProvider, LocalTranscriptionProvider>();
#pragma warning disable CS0618
builder.Services.AddSingleton<Chummer.Run.AI.Compatibility.ITranscriptionProvider>(sp =>
    new Chummer.Run.AI.Compatibility.LegacyTranscriptionProviderAdapter(sp.GetRequiredService<CanonicalTranscriptionProvider>()));
#pragma warning restore CS0618

builder.Services.AddHttpClient(GatewayProviderClientNames.BrowserAct, client =>
{
    var baseUrl = ResolveProviderSetting(builder.Configuration, "BrowserAct", "BaseUrl", "https://api.browseract.example");
    client.BaseAddress = new Uri(baseUrl, UriKind.Absolute);
});

builder.Services.AddHttpClient(GatewayProviderClientNames.PeekShot, client =>
{
    var baseUrl = ResolveProviderSetting(builder.Configuration, "PeekShot", "BaseUrl", "https://api.peekshot.example");
    client.BaseAddress = new Uri(baseUrl, UriKind.Absolute);
});

builder.Services.AddHttpClient(GatewayProviderClientNames.MarkupGo, client =>
{
    var baseUrl = ResolveProviderSetting(builder.Configuration, "MarkupGo", "BaseUrl", "https://api.markupgo.example");
    client.BaseAddress = new Uri(baseUrl, UriKind.Absolute);
});

var app = builder.Build();

// Configure the HTTP request pipeline.

app.UseHttpsRedirection();

app.UseMiddleware<AiMutationAuthorizationMiddleware>();

app.UseAuthorization();

app.MapAiPublicEndpoints();
app.MapControllers();

app.Run();

static IConfigurationSection ResolveProviderSection(IConfiguration configuration)
{
    var section = configuration.GetSection("AiGateway:Providers");
    if (section.Exists())
    {
        return section;
    }

    return configuration.GetSection("Providers");
}

static string ResolveProviderSetting(
    IConfiguration configuration,
    string provider,
    string key,
    string fallback)
{
    var section = ResolveProviderSection(configuration);
    return section[$"{provider}:{key}"] ?? fallback;
}

static Uri ResolveHubApiBaseAddress(IConfiguration configuration)
{
    string? configured = configuration["CHUMMER_HUB_API_BASE_URL"]
        ?? configuration["CHUMMER_API_BASE_URL"]
        ?? configuration["HubApi:BaseUrl"];
    string baseUrl = string.IsNullOrWhiteSpace(configured)
        ? "http://chummer-api:8080"
        : configured.Trim();
    if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out Uri? uri))
    {
        throw new InvalidOperationException($"Invalid Hub API base address '{baseUrl}'.");
    }

    return uri;
}
