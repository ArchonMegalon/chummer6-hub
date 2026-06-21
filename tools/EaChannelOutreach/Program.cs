using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

const string ChannelKind = "whatsapp_official_business";
const string DefaultSubjectId = "subject.ea.old-lady-outreach";
const string DefaultMessage =
    "Mei Schatz, ich hab deine Nachricht mit der neuen Nummer gesehen. " +
    "Bevor ich irgendwas glaube: Sag mir bitte etwas, das nur meine Tochter weiss, " +
    "und ruf mich ueber den alten Weg an, wenn du kannst. Ich schicke kein Geld " +
    "und keine Codes ueber WhatsApp.";

Options options = Options.Parse(args);
if (string.IsNullOrWhiteSpace(options.Recipient))
{
    WriteJson(new
    {
        status = "blocked",
        blockers = new[] { "recipient_required" },
        usage = "dotnet run --project tools/EaChannelOutreach -- --recipient '+43 ...' [--live]"
    });
    return 2;
}

string? recipientDigits = NormalizePhone(options.Recipient);
if (recipientDigits is null)
{
    WriteJson(new
    {
        status = "blocked",
        blockers = new[] { "recipient_invalid" },
        recipientMasked = MaskPhone(options.Recipient)
    });
    return 2;
}

string root = FindRepoRoot(AppContext.BaseDirectory);
string envPath = Path.GetFullPath(options.EnvFile ?? Path.Combine(root, ".env"));
string storePath = Path.GetFullPath(options.StorePath ?? Path.Combine(root, ".runtime-temp", "ea-outreach", "community-store.json"));
Directory.CreateDirectory(Path.GetDirectoryName(storePath)!);

Dictionary<string, string?> config = LoadEnvFile(envPath);
config["CHUMMER_COMMUNITY_STORE_PATH"] = storePath;
if (options.Live && !string.IsNullOrWhiteSpace(options.EaEnvFile))
{
    Dictionary<string, string?> eaConfig = LoadEnvFile(Path.GetFullPath(options.EaEnvFile));
    CopyIfPresent(eaConfig, "EA_API_TOKEN", config, "CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN");
    string? operatorPrincipal = FirstListValue(eaConfig.GetValueOrDefault("EA_OPERATOR_PRINCIPAL_IDS"));
    if (!string.IsNullOrWhiteSpace(operatorPrincipal))
    {
        config["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] = operatorPrincipal;
    }
    else
    {
        CopyIfPresent(eaConfig, "EA_DEFAULT_PRINCIPAL_ID", config, "CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID");
    }

    CopyIfPresent(eaConfig, "EA_WHATSAPP_WEB_DEFAULT_BINDING_ID", config, "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID");
    CopyIfPresent(eaConfig, "EA_WHATSAPP_DEFAULT_BINDING_ID", config, "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID");
}
if (!options.Live)
{
    foreach (string key in new[]
    {
        "CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN",
        "CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID",
        "CHUMMER_EA_CHANNEL_MESSAGING_EA_BINDING_ID",
        "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID",
        "CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID",
        "CHUMMER_EA_CHANNEL_MESSAGING_EA_TELEGRAM_BINDING_ID"
    })
    {
        config[key] = string.Empty;
    }
}
else if (!string.IsNullOrWhiteSpace(options.EaBaseUrl))
{
    config["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = options.EaBaseUrl.Trim();
}
if (options.Live && !string.IsNullOrWhiteSpace(options.EaWhatsappWebBindingId))
{
    config["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID"] = options.EaWhatsappWebBindingId.Trim();
}

if (options.Live && !string.IsNullOrWhiteSpace(options.EaWhatsappBindingId))
{
    config["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID"] = options.EaWhatsappBindingId.Trim();
}

IConfiguration configuration = new ConfigurationBuilder()
    .AddInMemoryCollection(config)
    .Build();

using var httpClient = new HttpClient();
var store = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
var accounts = new AccountService(store);
var links = new IdentityLinkService(store, accounts);
var messaging = new ExecutiveAssistantChannelMessagingService(
    httpClient,
    store,
    accounts,
    configuration,
    NullLogger<ExecutiveAssistantChannelMessagingService>.Instance);

string subjectId = string.IsNullOrWhiteSpace(options.SubjectId) ? DefaultSubjectId : options.SubjectId.Trim();
string message = string.IsNullOrWhiteSpace(options.Message) ? DefaultMessage : options.Message.Trim();
string idempotencyKey = string.IsNullOrWhiteSpace(options.IdempotencyKey)
    ? $"old-lady-outreach-{DateTimeOffset.UtcNow:yyyyMMddHHmmss}"
    : options.IdempotencyKey.Trim();

accounts.EnsureUserWithStatus(subjectId, "Old Lady Safety Fixture", email: null);
links.LinkChannel(new LinkChannelRequest(
    subjectId,
    ChannelKind,
    options.Recipient,
    NotificationsEnabled: true,
    Purpose: "old_lady_scam_response_test",
    AiSupportOpeningPrompt: "Reply cautiously to family-emergency new-number lures; never send money or codes."));
ChannelLinkDto channel = links.LinkChannelToExecutiveAssistant(
    ChannelKind,
    new LinkChannelToExecutiveAssistantRequest(
        subjectId,
        options.Recipient,
        Purpose: "old_lady_scam_response_test",
        AiSupportOpeningPrompt: "Reply cautiously to family-emergency new-number lures; never send money or codes.",
        NotificationsEnabled: true));

ExecutiveAssistantChannelSendResult result = await messaging.SendMessageAsync(
    subjectId,
    ChannelKind,
    new ExecutiveAssistantChannelSendRequest(
        MessageText: message,
        CounterpartyHandle: options.Recipient,
        ConversationId: null,
        IdempotencyKey: idempotencyKey),
    CancellationToken.None);

WriteJson(new
{
    status = result.Status,
    dryRun = !options.Live,
    live = options.Live,
    recipientMasked = MaskPhone(options.Recipient),
    channelKind = ChannelKind,
    channelStatus = channel.Status,
    conversationId = result.ConversationId,
    messageId = result.MessageId,
    deliveryRef = result.DeliveryRef,
    failureReason = result.FailureReason,
    duplicate = result.Duplicate,
    idempotencyKey = result.IdempotencyKey,
    storePath,
    messageText = message
});

return options.Live
    ? string.Equals(result.Status, "sent", StringComparison.OrdinalIgnoreCase) ? 0 : 2
    : string.Equals(result.Status, "suppressed_ea_unconfigured", StringComparison.OrdinalIgnoreCase)
        || string.Equals(result.Status, "sent", StringComparison.OrdinalIgnoreCase)
            ? 0
            : 2;

static Dictionary<string, string?> LoadEnvFile(string path)
{
    var values = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
    if (!File.Exists(path))
    {
        return values;
    }

    foreach (string raw in File.ReadLines(path))
    {
        string line = raw.Trim();
        if (line.Length == 0 || line.StartsWith('#') || !line.Contains('='))
        {
            continue;
        }

        int split = line.IndexOf('=');
        string key = line[..split].Trim();
        string value = line[(split + 1)..].Trim().Trim('"', '\'');
        if (key.Length > 0)
        {
            values[key] = value;
        }
    }

    return values;
}

static void CopyIfPresent(
    IReadOnlyDictionary<string, string?> source,
    string sourceKey,
    IDictionary<string, string?> target,
    string targetKey)
{
    if (source.TryGetValue(sourceKey, out string? value) && !string.IsNullOrWhiteSpace(value))
    {
        target[targetKey] = value.Trim();
    }
}

static string? FirstListValue(string? value)
{
    foreach (string part in (value ?? string.Empty).Replace(';', ',').Split(',', StringSplitOptions.RemoveEmptyEntries))
    {
        string normalized = part.Trim();
        if (normalized.Length > 0)
        {
            return normalized;
        }
    }

    return null;
}

static string? NormalizePhone(string value)
{
    string digits = new(value.Where(char.IsDigit).ToArray());
    return digits.Length >= 7 ? digits : null;
}

static string MaskPhone(string value)
{
    string digits = new(value.Where(char.IsDigit).ToArray());
    return digits.Length < 4 ? "[phone-redacted]" : $"[phone-redacted:*{digits[^4..]}]";
}

static string FindRepoRoot(string start)
{
    DirectoryInfo? current = new(start);
    while (current is not null)
    {
        if (File.Exists(Path.Combine(current.FullName, "Chummer.Run.sln")))
        {
            return current.FullName;
        }

        current = current.Parent;
    }

    return Directory.GetCurrentDirectory();
}

static void WriteJson(object payload)
{
    Console.WriteLine(JsonSerializer.Serialize(
        payload,
        new JsonSerializerOptions
        {
            WriteIndented = true
        }));
}

internal sealed record Options(
    string Recipient,
    string Message,
    string? EnvFile,
    string? StorePath,
    string? EaBaseUrl,
    string? EaEnvFile,
    string? EaWhatsappWebBindingId,
    string? EaWhatsappBindingId,
    string SubjectId,
    string IdempotencyKey,
    bool Live)
{
    private const string DefaultOptionSubjectId = "subject.ea.old-lady-outreach";

    public static Options Parse(string[] args)
    {
        string recipient = string.Empty;
        string message = string.Empty;
        string? envFile = null;
        string? storePath = null;
        string? eaBaseUrl = null;
        string? eaEnvFile = null;
        string? eaWhatsappWebBindingId = null;
        string? eaWhatsappBindingId = null;
        string subjectId = DefaultOptionSubjectId;
        string idempotencyKey = string.Empty;
        bool live = false;

        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];
            string? Next() => i + 1 < args.Length ? args[++i] : string.Empty;
            switch (arg)
            {
                case "--recipient":
                    recipient = Next() ?? string.Empty;
                    break;
                case "--message":
                    message = Next() ?? string.Empty;
                    break;
                case "--env-file":
                    envFile = Next();
                    break;
                case "--store-path":
                    storePath = Next();
                    break;
                case "--ea-base-url":
                    eaBaseUrl = Next();
                    break;
                case "--ea-env-file":
                    eaEnvFile = Next();
                    break;
                case "--ea-whatsapp-web-binding-id":
                    eaWhatsappWebBindingId = Next();
                    break;
                case "--ea-whatsapp-binding-id":
                    eaWhatsappBindingId = Next();
                    break;
                case "--subject-id":
                    subjectId = Next() ?? DefaultOptionSubjectId;
                    break;
                case "--idempotency-key":
                    idempotencyKey = Next() ?? string.Empty;
                    break;
                case "--live":
                    live = true;
                    break;
            }
        }

        return new Options(
            recipient,
            message,
            envFile,
            storePath,
            eaBaseUrl,
            eaEnvFile,
            eaWhatsappWebBindingId,
            eaWhatsappBindingId,
            subjectId,
            idempotencyKey,
            live);
    }
}
