namespace Chummer.Run.Api.Services.Support;

public sealed class AnswerlyRuntimePolicy
{
    public const string VerifiedFullAdapter = "verified_full_adapter";
    public const string VerifiedWidgetOnly = "verified_widget_only";
    public const string Unverified = "unverified";
    public const string Rejected = "rejected";

    private readonly IConfiguration _configuration;

    public AnswerlyRuntimePolicy(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public string VerificationState
    {
        get
        {
            string configured = Normalize(_configuration["ANSWERLY_PROVIDER_VERIFICATION_STATE"]);
            return configured switch
            {
                VerifiedFullAdapter => VerifiedFullAdapter,
                VerifiedWidgetOnly => VerifiedWidgetOnly,
                Rejected => Rejected,
                _ => Unverified
            };
        }
    }

    public bool AnswerlyEnabled => ReadBoolean("ANSWERLY_ENABLED", false);
    public bool SupportEnabled => ReadBoolean("ANSWERLY_SUPPORT_ENABLED", false);
    public bool HumanizerEnabled => ReadBoolean("ANSWERLY_HUMANIZER_ENABLED", false);
    public bool OpenAiCompatEnabled => ReadBoolean("ANSWERLY_OPENAI_COMPAT_ENABLED", false);

    public bool CanUseSupportAdapter =>
        AnswerlyEnabled
        && SupportEnabled
        && VerificationState is VerifiedFullAdapter or VerifiedWidgetOnly;

    public bool CanUseHumanizer =>
        AnswerlyEnabled
        && HumanizerEnabled
        && VerificationState == VerifiedFullAdapter;

    public bool CanUseOpenAiCompat =>
        AnswerlyEnabled
        && SupportEnabled
        && OpenAiCompatEnabled
        && VerificationState == VerifiedFullAdapter;

    private bool ReadBoolean(string key, bool defaultValue)
    {
        string raw = Normalize(_configuration[key]);
        return raw switch
        {
            "1" or "true" or "yes" or "on" => true,
            "0" or "false" or "no" or "off" => false,
            _ => defaultValue
        };
    }

    private static string Normalize(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : value.Trim().ToLowerInvariant();
}
