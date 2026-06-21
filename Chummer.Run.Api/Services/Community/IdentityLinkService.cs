using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class IdentityLinkService
{
    private const string AiSupportOnlyPurpose = "ai_support_only";
    private const string WhatsappAiSupportOpeningPrompt =
        "Ask what questions the user has before giving product guidance.";
    private const string WhatsappAiSupportNote =
        "WhatsApp is stored only for support outreach. When support reaches out, it asks what questions the user has before helping. It is not used for account access, recovery, marketing, or public profile display.";

    private static readonly string[] SupportedIdentityProviders =
    {
        "email",
        "google",
        "facebook",
        "telegram"
    };

    private static readonly string[] SupportedChannels =
    {
        "telegram_official_bot",
        "whatsapp_official_business"
    };

    private static readonly string[] FutureCapabilities =
    {
        "telegram_user_bot",
        "facebook_login_optional",
        "provider_callbacks"
    };

    private readonly CommunityStore _store;
    private readonly AccountService _accounts;

    public IdentityLinkService(CommunityStore store, AccountService accounts)
    {
        _store = store;
        _accounts = accounts;
    }

    public AccountLinkSummaryDto GetSummary(string subjectId)
    {
        var user = _accounts.EnsureUser(subjectId, subjectId);
        lock (_store.Gate)
        {
            var identities = _store.LinkedIdentities
                .Where(link => string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static link => link.IsPrimary)
                .ThenBy(static link => link.Provider, StringComparer.OrdinalIgnoreCase)
                .Select(RedactIdentityForSummary)
                .ToArray();
            var channels = _store.ChannelLinks
                .Where(link => string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .OrderBy(static link => link.ChannelKind, StringComparer.OrdinalIgnoreCase)
                .Select(RedactChannelForSummary)
                .ToArray();

            return new AccountLinkSummaryDto(
                user,
                identities,
                channels,
                RecommendedPrimaryAuth(identities),
                RecoveryPosture(identities),
                OrchestratorBrain: "EA",
                OfficialCompanionChannel: "telegram_official_bot",
                SupportedIdentityProviders,
                SupportedChannels,
                FutureCapabilities);
        }
    }

    public LinkedIdentityDto? FindLinkedIdentity(string provider, string providerSubject)
    {
        var normalizedProvider = NormalizeProvider(provider);
        var normalizedSubject = AccountService.NormalizeOptional(providerSubject);
        if (normalizedSubject is null)
        {
            return null;
        }

        lock (_store.Gate)
        {
            return _store.LinkedIdentities.FirstOrDefault(link =>
                string.Equals(link.Provider, normalizedProvider, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ProviderSubject, normalizedSubject, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(link.Status, "revoked", StringComparison.OrdinalIgnoreCase));
        }
    }

    public LinkedIdentityDto? FindLinkedIdentityForUser(string userId, string provider)
    {
        var normalizedUserId = AccountService.NormalizeOptional(userId);
        if (normalizedUserId is null)
        {
            return null;
        }

        var normalizedProvider = NormalizeProvider(provider);
        lock (_store.Gate)
        {
            return _store.LinkedIdentities.FirstOrDefault(link =>
                string.Equals(link.UserId, normalizedUserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.Provider, normalizedProvider, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(link.Status, "revoked", StringComparison.OrdinalIgnoreCase));
        }
    }

    public LinkedIdentityDto LinkEmail(LinkEmailIdentityRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId, nameof(request.SubjectId));
        var email = AccountService.NormalizeRequired(request.Email, nameof(request.Email)).ToLowerInvariant();
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            var existingIndex = _store.LinkedIdentities.FindIndex(link =>
                string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.Provider, "email", StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ProviderSubject, email, StringComparison.OrdinalIgnoreCase));

            if (existingIndex >= 0)
            {
                var existing = _store.LinkedIdentities[existingIndex];
                if (request.MakePrimary)
                {
                    DemotePrimaryAuthLocked(user.UserId);
                }

                var updated = existing with
                {
                    DisplayLabel = email,
                    IsPrimary = request.MakePrimary || existing.IsPrimary,
                    UpdatedAtUtc = now,
                    Note = "Email verification is pending until the transactional mail callback confirms the link."
                };
                _store.LinkedIdentities[existingIndex] = updated;
                _store.PersistLocked();
                return updated;
            }

            if (request.MakePrimary)
            {
                DemotePrimaryAuthLocked(user.UserId);
            }

            var created = new LinkedIdentityDto(
                IdentityLinkId: AccountService.NewId("idl"),
                UserId: user.UserId,
                Provider: "email",
                LinkKind: "password_or_magic_link",
                ProviderSubject: email,
                DisplayLabel: email,
                Status: "pending_verification",
                VerificationPolicy: "required",
                IsPrimary: request.MakePrimary,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                VerifiedAtUtc: null,
                Note: "Email verification is pending until the transactional mail callback confirms the link.");
            _store.LinkedIdentities.Add(created);
            _store.PersistLocked();
            return created;
        }
    }

    public LinkedIdentityDto ConfirmIdentityLink(ConfirmIdentityLinkRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId, nameof(request.SubjectId));
        var identityLinkId = AccountService.NormalizeRequired(request.IdentityLinkId, nameof(request.IdentityLinkId));
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            var index = _store.LinkedIdentities.FindIndex(link =>
                string.Equals(link.IdentityLinkId, identityLinkId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
            if (index < 0)
            {
                throw new KeyNotFoundException($"Unknown identity link: {identityLinkId}");
            }

            var existing = _store.LinkedIdentities[index];
            var updated = existing with
            {
                Status = existing.Provider.Equals("email", StringComparison.OrdinalIgnoreCase)
                    ? "verified"
                    : "provider_backed",
                VerificationPolicy = existing.Provider.Equals("email", StringComparison.OrdinalIgnoreCase)
                    ? "required"
                    : "provider_backed",
                VerifiedAtUtc = now,
                UpdatedAtUtc = now,
                Note = existing.Provider.Equals("email", StringComparison.OrdinalIgnoreCase)
                    ? "Email link confirmed."
                    : "Provider-backed identity link confirmed."
            };
            _store.LinkedIdentities[index] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    public LinkedIdentityDto LinkExternalIdentity(LinkExternalIdentityRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId, nameof(request.SubjectId));
        var provider = NormalizeProvider(request.Provider);
        var providerSubject = AccountService.NormalizeRequired(request.ProviderSubject, nameof(request.ProviderSubject));
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            var conflictingIndex = _store.LinkedIdentities.FindIndex(link =>
                string.Equals(link.Provider, provider, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ProviderSubject, providerSubject, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(link.Status, "revoked", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
            if (conflictingIndex >= 0)
            {
                throw new InvalidOperationException($"This {provider} identity is already linked to another Chummer account.");
            }

            var existingIndex = _store.LinkedIdentities.FindIndex(link =>
                string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.Provider, provider, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ProviderSubject, providerSubject, StringComparison.OrdinalIgnoreCase));
            if (request.MakePrimary)
            {
                DemotePrimaryAuthLocked(user.UserId);
            }

            var status = provider switch
            {
                "telegram" => "linked",
                _ => "provider_backed"
            };
            var verificationPolicy = provider switch
            {
                "telegram" => "channel_identity",
                _ => "provider_backed"
            };
            var displayLabel = AccountService.NormalizeOptional(request.DisplayLabel) ?? providerSubject;
            var note = provider switch
            {
                "google" => "Google is the preferred mainstream social bootstrap for Hub onboarding.",
                "facebook" => "Facebook remains optional and should stay demand-driven rather than default.",
                "telegram" => "Telegram identity linking is separate from channel/bot routing.",
                _ => null
            };

            if (existingIndex >= 0)
            {
                var updated = _store.LinkedIdentities[existingIndex] with
                {
                    DisplayLabel = displayLabel,
                    Status = status,
                    VerificationPolicy = verificationPolicy,
                    IsPrimary = request.MakePrimary || _store.LinkedIdentities[existingIndex].IsPrimary,
                    UpdatedAtUtc = now,
                    VerifiedAtUtc = now,
                    Note = note
                };
                _store.LinkedIdentities[existingIndex] = updated;
                _store.PersistLocked();
                return updated;
            }

            var created = new LinkedIdentityDto(
                IdentityLinkId: AccountService.NewId("idl"),
                UserId: user.UserId,
                Provider: provider,
                LinkKind: provider == "telegram" ? "linked_identity" : "social_auth",
                ProviderSubject: providerSubject,
                DisplayLabel: displayLabel,
                Status: status,
                VerificationPolicy: verificationPolicy,
                IsPrimary: request.MakePrimary,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                VerifiedAtUtc: now,
                Note: note);
            _store.LinkedIdentities.Add(created);
            _store.PersistLocked();
            return created;
        }
    }

    public ChannelLinkDto LinkChannel(LinkChannelRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId, nameof(request.SubjectId));
        var channelKind = NormalizeChannelKind(request.ChannelKind);
        var channelHandle = AccountService.NormalizeOptional(request.ChannelHandle) ?? channelKind;
        var normalizedHandle = NormalizeRequiredChannelHandle(channelKind, channelHandle);
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            var existingIndex = _store.ChannelLinks.FindIndex(link =>
                string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase));

            var status = channelKind switch
            {
                "telegram_official_bot" => "pending_verification",
                "whatsapp_official_business" => "linked",
                "telegram_user_bot" => "future_capability",
                _ => "linked"
            };
            var note = channelKind switch
            {
                "telegram_official_bot" => "Telegram companion linking stays pending until the official bot confirms the account handshake.",
                "whatsapp_official_business" => WhatsappAiSupportNote,
                "telegram_user_bot" => "Bring-your-own Telegram bots are intentionally deferred until ownership, verification, and policy controls are stronger.",
                _ => null
            };
            var official = channelKind is "telegram_official_bot" or "whatsapp_official_business";
            var purpose = ResolveChannelPurpose(channelKind, request.Purpose);
            var aiSupportOpeningPrompt = ResolveAiSupportOpeningPrompt(channelKind, request.AiSupportOpeningPrompt);

            if (existingIndex >= 0)
            {
                var updated = _store.ChannelLinks[existingIndex] with
                {
                    DisplayLabel = normalizedHandle,
                    Status = status,
                    NotificationsEnabled = request.NotificationsEnabled,
                    UpdatedAtUtc = now,
                    Note = note,
                    Purpose = purpose,
                    AiSupportOpeningPrompt = aiSupportOpeningPrompt
                };
                _store.ChannelLinks[existingIndex] = updated;
                _store.PersistLocked();
                return updated;
            }

            var created = new ChannelLinkDto(
                ChannelLinkId: AccountService.NewId("chn"),
                UserId: user.UserId,
                ChannelKind: channelKind,
                DisplayLabel: normalizedHandle,
                Status: status,
                OfficialChannel: official,
                NotificationsEnabled: request.NotificationsEnabled,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                Note: note)
            {
                Purpose = purpose,
                AiSupportOpeningPrompt = aiSupportOpeningPrompt
            };
            _store.ChannelLinks.Add(created);
            _store.PersistLocked();
            return created;
        }
    }

    public ChannelLinkDto LinkChannelToExecutiveAssistant(string channelKind, LinkChannelToExecutiveAssistantRequest request)
    {
        var subjectId = AccountService.NormalizeRequired(request.SubjectId, nameof(request.SubjectId));
        var normalizedChannelKind = NormalizeChannelKind(channelKind);
        var requestedChannelHandle = NormalizeOptionalChannelHandle(
            normalizedChannelKind,
            AccountService.NormalizeOptional(request.ChannelHandle));
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;
        var purpose = ResolveChannelPurpose(normalizedChannelKind, request.Purpose);
        var aiSupportOpeningPrompt = ResolveAiSupportOpeningPrompt(normalizedChannelKind, request.AiSupportOpeningPrompt);
        var note = normalizedChannelKind == "whatsapp_official_business"
            ? WhatsappAiSupportNote
            : "Channel is now linked.";

        lock (_store.Gate)
        {
            var existingIndex = _store.ChannelLinks.FindIndex(link =>
                string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ChannelKind, normalizedChannelKind, StringComparison.OrdinalIgnoreCase));

            if (existingIndex < 0)
            {
                if (requestedChannelHandle is null)
                {
                    throw new InvalidOperationException(
                        $"No existing {normalizedChannelKind} channel is linked for this account. Save a channel handle first or send it in the request.");
                }

                var created = new ChannelLinkDto(
                    ChannelLinkId: AccountService.NewId("chn"),
                    UserId: user.UserId,
                    ChannelKind: normalizedChannelKind,
                    DisplayLabel: requestedChannelHandle,
                    Status: "ea_linked",
                    OfficialChannel: normalizedChannelKind is "telegram_official_bot" or "whatsapp_official_business",
                    NotificationsEnabled: ResolveChannelNotificationsEnabled(normalizedChannelKind, request.NotificationsEnabled, existing: null),
                    CreatedAtUtc: now,
                    UpdatedAtUtc: now,
                    Note: note)
                {
                    Purpose = purpose,
                    AiSupportOpeningPrompt = aiSupportOpeningPrompt
                };

                _store.ChannelLinks.Add(created);
                _store.PersistLocked();
                return created;
            }

            var existing = _store.ChannelLinks[existingIndex];
            var displayLabel = requestedChannelHandle
                ?? NormalizeOptionalChannelHandle(normalizedChannelKind, existing.DisplayLabel)
                ?? existing.DisplayLabel;

            var updated = existing with
            {
                DisplayLabel = displayLabel,
                Status = "ea_linked",
                NotificationsEnabled = ResolveChannelNotificationsEnabled(normalizedChannelKind, request.NotificationsEnabled, existing.NotificationsEnabled),
                UpdatedAtUtc = now,
                Note = note,
                Purpose = purpose,
                AiSupportOpeningPrompt = aiSupportOpeningPrompt
            };

            _store.ChannelLinks[existingIndex] = updated;
            _store.PersistLocked();
            return updated;
        }
    }

    public ChannelDeepLinkResponse GetChannelDeepLink(string subjectId, string channelKind, string? channelHandle)
    {
        var normalizedSubjectId = AccountService.NormalizeRequired(subjectId, nameof(subjectId));
        var normalizedChannelKind = NormalizeChannelKind(channelKind);
        var user = _accounts.EnsureUser(normalizedSubjectId, normalizedSubjectId);

        string? resolvedHandle;
        lock (_store.Gate)
        {
            var stored = _store.ChannelLinks.FirstOrDefault(link =>
                string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ChannelKind, normalizedChannelKind, StringComparison.OrdinalIgnoreCase));

            resolvedHandle = AccountService.NormalizeOptional(channelHandle) ?? stored?.DisplayLabel;
        }

        if (resolvedHandle is null)
        {
            throw new ArgumentException($"A channel handle is required for {normalizedChannelKind}.");
        }

        var normalizedHandle = NormalizeOptionalChannelHandle(normalizedChannelKind, resolvedHandle)
            ?? throw new ArgumentException($"A valid channel handle is required for {normalizedChannelKind}.");

        var (normalizedChannelHandle, deepLink, alternateDeepLink) = BuildChannelDeepLink(normalizedChannelKind, normalizedHandle);

        return new ChannelDeepLinkResponse(
            ChannelKind: normalizedChannelKind,
            ChannelHandle: normalizedChannelHandle,
            DeepLink: deepLink,
            QrImageUrl: BuildQrImageUrl(deepLink),
            AlternateDeepLink: alternateDeepLink);
    }

    private static LinkedIdentityDto RedactIdentityForSummary(LinkedIdentityDto link)
        => link with
        {
            ProviderSubject = string.Equals(link.Provider, "email", StringComparison.OrdinalIgnoreCase)
                ? link.DisplayLabel
                : "hidden",
            Note = null,
        };

    private static ChannelLinkDto RedactChannelForSummary(ChannelLinkDto link)
        => link with
        {
            Note = null,
        };

    private static string ResolveChannelPurpose(string channelKind, string? requestedPurpose)
    {
        if (string.Equals(channelKind, "whatsapp_official_business", StringComparison.OrdinalIgnoreCase))
        {
            return AiSupportOnlyPurpose;
        }

        return AccountService.NormalizeOptional(requestedPurpose) ?? string.Empty;
    }

    private static string ResolveAiSupportOpeningPrompt(string channelKind, string? requestedPrompt)
    {
        if (string.Equals(channelKind, "whatsapp_official_business", StringComparison.OrdinalIgnoreCase))
        {
            return AccountService.NormalizeOptional(requestedPrompt) ?? WhatsappAiSupportOpeningPrompt;
        }

        return AccountService.NormalizeOptional(requestedPrompt) ?? string.Empty;
    }

    private static bool ResolveChannelNotificationsEnabled(string channelKind, bool? requested, bool? existing)
    {
        if (requested.HasValue)
        {
            return requested.Value;
        }

        if (existing.HasValue)
        {
            return existing.Value;
        }

        return !string.Equals(channelKind, "whatsapp_official_business", StringComparison.OrdinalIgnoreCase);
    }

    private void DemotePrimaryAuthLocked(string userId)
    {
        for (var i = 0; i < _store.LinkedIdentities.Count; i++)
        {
            var existing = _store.LinkedIdentities[i];
            if (!string.Equals(existing.UserId, userId, StringComparison.OrdinalIgnoreCase) || !existing.IsPrimary)
            {
                continue;
            }

            _store.LinkedIdentities[i] = existing with
            {
                IsPrimary = false,
                UpdatedAtUtc = DateTimeOffset.UtcNow
            };
        }
    }

    private static string RecommendedPrimaryAuth(IReadOnlyList<LinkedIdentityDto> identities)
    {
        var primary = identities.FirstOrDefault(static link => link.IsPrimary && link.Status != "revoked");
        if (primary is not null)
        {
            return primary.Provider;
        }

        if (identities.Any(static link => link.Provider == "google" && link.Status == "provider_backed"))
        {
            return "google";
        }

        if (identities.Any(static link => link.Provider == "email" && (link.Status == "verified" || link.Status == "pending_verification")))
        {
            return "email";
        }

        return "email";
    }

    private static string RecoveryPosture(IReadOnlyList<LinkedIdentityDto> identities)
    {
        if (identities.Any(static link => link.Provider == "email" && link.Status == "verified"))
        {
            return "verified_email";
        }

        if (identities.Any(static link => (link.Provider == "google" || link.Provider == "facebook") && link.Status == "provider_backed"))
        {
            return "provider_backed";
        }

        if (identities.Any(static link => link.Provider == "email" && link.Status == "pending_verification"))
        {
            return "awaiting_email_verification";
        }

        return "recovery_unset";
    }

    private static (string NormalizedHandle, string DeepLink, string? AlternateDeepLink) BuildChannelDeepLink(string channelKind, string rawHandle)
    {
        return channelKind switch
        {
            "telegram_official_bot" => BuildTelegramDeepLink(rawHandle),
            "whatsapp_official_business" => BuildWhatsappDeepLink(rawHandle),
            "telegram_user_bot" => BuildTelegramDeepLink(rawHandle),
            _ => throw new ArgumentException($"Unsupported channel kind '{channelKind}'.")
        };
    }

    private static string BuildQrImageUrl(string deepLink)
        => $"https://api.qrserver.com/v1/create-qr-code/?size=640x640&margin=16&data={Uri.EscapeDataString(deepLink)}";

    private static (string NormalizedHandle, string DeepLink, string? AlternateDeepLink) BuildTelegramDeepLink(string rawHandle)
    {
        var normalizedHandle = NormalizeTelegramHandle(rawHandle);
        var deepLink = $"https://t.me/{Uri.EscapeDataString(normalizedHandle)}";
        return (normalizedHandle, deepLink, $"https://telegram.me/{Uri.EscapeDataString(normalizedHandle)}");
    }

    private static (string NormalizedHandle, string DeepLink, string? AlternateDeepLink) BuildWhatsappDeepLink(string rawHandle)
    {
        string digits = NormalizeWhatsappHandle(rawHandle);
        return (digits, $"https://wa.me/{digits}", $"whatsapp://send?phone={digits}");
    }

    private static string NormalizeWhatsappHandle(string rawHandle)
    {
        var digits = new string(rawHandle.Where(char.IsDigit).ToArray());
        if (digits.Length < 7)
        {
            throw new ArgumentException("WhatsApp number must include country code and at least 7 digits.");
        }

        return digits;
    }

    private static string NormalizeChannelHandleForDisplay(string channelKind, string rawHandle)
        => channelKind switch
        {
            "whatsapp_official_business" => NormalizeWhatsappHandle(rawHandle),
            "telegram_official_bot" => NormalizeTelegramHandle(rawHandle),
            "telegram_user_bot" => NormalizeTelegramHandle(rawHandle),
            _ => rawHandle.Trim()
        };

    private static string? NormalizeOptionalChannelHandle(string channelKind, string? rawHandle)
        => string.IsNullOrWhiteSpace(rawHandle)
            ? null
            : NormalizeChannelHandleForDisplay(channelKind, rawHandle);

    private static string NormalizeRequiredChannelHandle(string channelKind, string rawHandle)
        => NormalizeOptionalChannelHandle(channelKind, rawHandle)
           ?? throw new ArgumentException("Channel handle is required.");

    private static string NormalizeTelegramHandle(string rawHandle)
    {
        string trimmed = rawHandle.Trim();
        if (trimmed.StartsWith("@", StringComparison.OrdinalIgnoreCase))
        {
            trimmed = trimmed[1..];
        }

        if (Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? uri)
            && uri.Host.StartsWith("t.me", StringComparison.OrdinalIgnoreCase))
        {
            string path = uri.AbsolutePath.Trim('/');
            if (!string.IsNullOrWhiteSpace(path))
            {
                return path.Split('/', StringSplitOptions.RemoveEmptyEntries)[0].Trim();
            }

            string queryHandle = TryReadQueryParameter(uri.Query, "start") ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(queryHandle))
            {
                return queryHandle.TrimStart('@');
            }
        }

        if (trimmed.StartsWith("tg://", StringComparison.OrdinalIgnoreCase)
            && Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? deepLinkUri))
        {
            string domain = deepLinkUri.Host;
            if (!string.IsNullOrWhiteSpace(domain) && !string.Equals(domain, "resolve", StringComparison.OrdinalIgnoreCase))
            {
                return domain;
            }

            string queryDomain = TryReadQueryParameter(deepLinkUri.Query, "domain") ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(queryDomain))
            {
                return queryDomain.TrimStart('@');
            }
        }

        if (trimmed.Contains(' ') )
        {
            trimmed = trimmed.Replace(" ", string.Empty);
        }

        if (trimmed.Length == 0)
        {
            throw new ArgumentException("Telegram handle cannot be empty.");
        }

        return trimmed;
    }

    private static string? TryReadQueryParameter(string query, string key)
    {
        if (string.IsNullOrWhiteSpace(query))
        {
            return null;
        }

        var normalizedKey = key.Trim().ToLowerInvariant();
        foreach (string pair in query.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            int separator = pair.IndexOf('=');
            if (separator <= 0)
            {
                continue;
            }

            string candidateKey = Uri.UnescapeDataString(pair[..separator]).ToLowerInvariant();
            if (!string.Equals(candidateKey, normalizedKey, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            return Uri.UnescapeDataString(pair[(separator + 1)..]);
        }

        return null;
    }

    private static string NormalizeProvider(string value)
    {
        var provider = AccountService.NormalizeRequired(value, nameof(value)).ToLowerInvariant();
        if (!SupportedIdentityProviders.Contains(provider, StringComparer.OrdinalIgnoreCase))
        {
            throw new ArgumentException($"Unsupported identity provider '{provider}'.");
        }

        return provider;
    }

    private static string NormalizeChannelKind(string value)
    {
        var normalized = AccountService.NormalizeRequired(value, nameof(value)).ToLowerInvariant();
        return normalized switch
        {
            "telegram_official_bot" => normalized,
            "telegram_user_bot" => normalized,
            "whatsapp_official_business" => normalized,
            _ => throw new ArgumentException($"Unsupported channel kind '{normalized}'.")
        };
    }
}
