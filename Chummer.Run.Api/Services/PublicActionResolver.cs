using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicActionResolver
{
    private static readonly string[] GenericLabels =
    {
        "open",
        "open the artifact detail",
        "open the roadmap detail",
        "read the linked detail",
        "read more",
        "learn more",
        "continue"
    };

    public ResolvedPublicActionViewModel ResolveFeatureAction(PublicFeatureCardDto card, bool authenticated, string currentPath)
    {
        var href = ResolveHref(card, authenticated);
        var label = ResolveLabel(card, href);
        var external = PublicUrlPolicy.IsExternalHref(href);
        var tone = ResolveTone(card);
        var current = IsSameRoute(href, currentPath);

        return new ResolvedPublicActionViewModel(label, href, tone, external, current);
    }

    public ResolvedPublicActionViewModel ResolvePrimaryExperienceAction(PublicFeatureCardDto card, bool authenticated, string currentPath)
    {
        var primaryCard = card with
        {
            DetailRoute = null,
            ActionLabel = null
        };

        var href = ResolveHref(primaryCard, authenticated);
        var label = ResolveLabel(primaryCard, href);
        var external = PublicUrlPolicy.IsExternalHref(href);
        return new ResolvedPublicActionViewModel(label, href, ResolveTone(primaryCard), external, IsSameRoute(href, currentPath));
    }

    public ResolvedPublicActionViewModel ResolveDetailPrimaryAction(PublicFeatureCardDto card, bool authenticated, string currentPath)
    {
        var detailCard = card with
        {
            Href = card.DetailPrimaryHref ?? card.Href,
            DetailRoute = null,
            ActionLabel = card.DetailPrimaryLabel ?? card.ActionLabel
        };

        var href = ResolveHref(detailCard, authenticated);
        var label = ResolveLabel(detailCard, href);
        var external = PublicUrlPolicy.IsExternalHref(href);
        return new ResolvedPublicActionViewModel(label, href, ResolveTone(detailCard), external, IsSameRoute(href, currentPath));
    }

    public void ValidateActionableCard(PublicFeatureCardDto card, IReadOnlySet<string> allowedRoutes)
    {
        var routeCandidates = new[]
        {
            card.Href,
            card.DetailRoute,
            card.FallbackRoute,
            card.GuestHref,
            card.RegisteredHref,
            card.DetailPrimaryHref
        };

        if (routeCandidates.All(string.IsNullOrWhiteSpace))
        {
            throw new InvalidOperationException($"public feature card '{card.Id}' has no actionable route.");
        }

        foreach (var candidate in routeCandidates.Where(static value => !string.IsNullOrWhiteSpace(value)))
        {
            if (PublicUrlPolicy.IsExternalHref(candidate))
            {
                continue;
            }

            var normalized = PublicRouteCatalog.NormalizeRoute(candidate!);
            if (!PublicRouteCatalog.Contains(normalized, allowedRoutes))
            {
                throw new InvalidOperationException($"public feature card '{card.Id}' points at missing route '{candidate}'.");
            }
        }

        ValidateLabel(card.Id, "action_label", card.ActionLabel);
        ValidateLabel(card.Id, "detail_primary_label", card.DetailPrimaryLabel);
        ValidateLabel(card.Id, "fallback_label", card.FallbackLabel);
    }

    private static string ResolveHref(PublicFeatureCardDto card, bool authenticated)
    {
        var preferred = authenticated ? card.RegisteredHref : card.GuestHref;
        return preferred
               ?? card.DetailRoute
               ?? card.Href
               ?? card.FallbackRoute
               ?? "/";
    }

    private static string ResolveLabel(PublicFeatureCardDto card, string href)
    {
        if (!string.IsNullOrWhiteSpace(card.ActionLabel))
        {
            return card.ActionLabel!;
        }

        if (PublicUrlPolicy.IsExternalHref(href))
        {
            if (!string.IsNullOrWhiteSpace(card.FallbackLabel))
            {
                return card.FallbackLabel!;
            }

            return card.Bucket switch
            {
                "coming_next" => "Read the horizon brief",
                "featured_artifacts" => "Open the external release brief",
                "supporting_reads" => "Read the external guide",
                _ => "Read the external brief"
            };
        }

        return card.Bucket switch
        {
            "featured_artifacts" when string.Equals(card.Badge, "Available today", StringComparison.OrdinalIgnoreCase) => "Open the live artifact",
            "featured_artifacts" => "Inspect the preview concept",
            "coming_next" => "Read the concept page",
            "whats_real_now" when string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase) => "See what works now",
            "whats_real_now" => "See current release",
            "choose_your_lane" => "See the lane fit",
            "participate" when href.Contains("/participate/codex", StringComparison.OrdinalIgnoreCase) => "Authorize contribution access",
            "participate" when href.Contains("/account/participation", StringComparison.OrdinalIgnoreCase) || href.Contains("/account/settings", StringComparison.OrdinalIgnoreCase) || href.Contains("#beta-interest", StringComparison.OrdinalIgnoreCase) => "Join beta waitlist",
            "participate" when href.Contains("/signup", StringComparison.OrdinalIgnoreCase) => "Claim your copy",
            "participate" when href.Contains("/login", StringComparison.OrdinalIgnoreCase) => "Sign in to continue",
            "participate" => "Open the participation path",
            _ => "See the next product step"
        };
    }

    private static string ResolveTone(PublicFeatureCardDto card)
        => card.Bucket switch
        {
            "start_here" => "secondary",
            "whats_real_now" => "ghost",
            "featured_artifacts" when string.Equals(card.Badge, "Available today", StringComparison.OrdinalIgnoreCase) => "secondary",
            "participate" => "secondary",
            _ => "ghost"
        };

    private static bool IsSameRoute(string href, string currentPath)
        => string.Equals(PublicRouteCatalog.NormalizeRoute(href), PublicRouteCatalog.NormalizeRoute(currentPath), StringComparison.OrdinalIgnoreCase);

    private static void ValidateLabel(string cardId, string fieldName, string? label)
    {
        if (string.IsNullOrWhiteSpace(label))
        {
            return;
        }

        if (GenericLabels.Contains(label.Trim(), StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"public feature card '{cardId}' uses a generic {fieldName} '{label}'.");
        }
    }
}
