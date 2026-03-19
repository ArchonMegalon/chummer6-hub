using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class IdentityLinkService
{
    private static readonly string[] SupportedIdentityProviders =
    {
        "email",
        "google",
        "facebook",
        "telegram"
    };

    private static readonly string[] SupportedChannels =
    {
        "telegram_official_bot"
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
                .ToArray();
            var channels = _store.ChannelLinks
                .Where(link => string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .OrderBy(static link => link.ChannelKind, StringComparer.OrdinalIgnoreCase)
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
        var user = _accounts.EnsureUser(subjectId, subjectId);
        var now = DateTimeOffset.UtcNow;

        lock (_store.Gate)
        {
            var existingIndex = _store.ChannelLinks.FindIndex(link =>
                string.Equals(link.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase)
                && string.Equals(link.DisplayLabel, channelHandle, StringComparison.OrdinalIgnoreCase));

            var status = channelKind switch
            {
                "telegram_official_bot" => "active",
                "telegram_user_bot" => "future_capability",
                _ => "linked"
            };
            var note = channelKind switch
            {
                "telegram_official_bot" => "Hub owns account, routing, permissions, and entitlements; EA stays the orchestrator brain behind the official bot.",
                "telegram_user_bot" => "Bring-your-own Telegram bots are intentionally deferred until ownership, verification, and policy controls are stronger.",
                _ => null
            };
            var official = channelKind == "telegram_official_bot";

            if (existingIndex >= 0)
            {
                var updated = _store.ChannelLinks[existingIndex] with
                {
                    Status = status,
                    NotificationsEnabled = request.NotificationsEnabled,
                    UpdatedAtUtc = now,
                    Note = note
                };
                _store.ChannelLinks[existingIndex] = updated;
                _store.PersistLocked();
                return updated;
            }

            var created = new ChannelLinkDto(
                ChannelLinkId: AccountService.NewId("chn"),
                UserId: user.UserId,
                ChannelKind: channelKind,
                DisplayLabel: channelHandle,
                Status: status,
                OfficialChannel: official,
                NotificationsEnabled: request.NotificationsEnabled,
                CreatedAtUtc: now,
                UpdatedAtUtc: now,
                Note: note);
            _store.ChannelLinks.Add(created);
            _store.PersistLocked();
            return created;
        }
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
            _ => throw new ArgumentException($"Unsupported channel kind '{normalized}'.")
        };
    }
}
