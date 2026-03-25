using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicActionResolver
{
    private static readonly string[] GenericLabels =
    {
        "open",
        "read more",
        "learn more",
        "continue"
    };

    public ResolvedPublicActionViewModel ResolveFeatureAction(PublicFeatureCardDto card, bool authenticated, string currentPath)
    {
        var href = ResolveHref(card, authenticated);
        var label = ResolveLabel(card, href);
        var external = Uri.TryCreate(href, UriKind.Absolute, out _);
        var tone = ResolveTone(card);
        var current = IsSameRoute(href, currentPath);

        return new ResolvedPublicActionViewModel(label, href, tone, external, current);
    }

    public void ValidateActionableCard(PublicFeatureCardDto card, IReadOnlySet<string> allowedRoutes)
    {
        var routeCandidates = new[]
        {
            card.Href,
            card.DetailRoute,
            card.FallbackRoute,
            card.GuestHref,
            card.RegisteredHref
        };

        foreach (var candidate in routeCandidates.Where(static value => !string.IsNullOrWhiteSpace(value)))
        {
            if (Uri.TryCreate(candidate, UriKind.Absolute, out _))
            {
                continue;
            }

            var normalized = NormalizeRoute(candidate!);
            if (!allowedRoutes.Contains(normalized))
            {
                throw new InvalidOperationException($"public feature card '{card.Id}' points at missing route '{candidate}'.");
            }
        }

        ValidateLabel(card.Id, "action_label", card.ActionLabel);
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

        if (Uri.TryCreate(href, UriKind.Absolute, out _))
        {
            return !string.IsNullOrWhiteSpace(card.FallbackLabel)
                ? card.FallbackLabel!
                : "Read the linked detail";
        }

        return card.Bucket switch
        {
            "featured_artifacts" when string.Equals(card.Badge, "Available today", StringComparison.OrdinalIgnoreCase) => "Open the live artifact",
            "featured_artifacts" => "Inspect the preview concept",
            "coming_next" => "Read the concept page",
            "whats_real_now" when string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase) => "Inspect the live proof",
            "whats_real_now" => "See the preview proof",
            "choose_your_lane" => "See the lane fit",
            "participate" when href.Contains("/signup", StringComparison.OrdinalIgnoreCase) => "Create account to continue",
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

    private static string NormalizeRoute(string href)
    {
        var trimmed = href.Trim();
        var hash = trimmed.IndexOf('#');
        if (hash >= 0)
        {
            trimmed = trimmed[..hash];
        }

        var query = trimmed.IndexOf('?');
        if (query >= 0)
        {
            trimmed = trimmed[..query];
        }

        return string.IsNullOrWhiteSpace(trimmed) ? "/" : trimmed;
    }

    private static bool IsSameRoute(string href, string currentPath)
        => string.Equals(NormalizeRoute(href), NormalizeRoute(currentPath), StringComparison.OrdinalIgnoreCase);

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
