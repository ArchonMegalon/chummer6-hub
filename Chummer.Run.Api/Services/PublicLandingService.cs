using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed class PublicLandingService
{
    private const string ManifestRelativePath = ".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml";
    private const string FeatureRegistryRelativePath = ".codex-design/product/PUBLIC_FEATURE_REGISTRY.yaml";
    private const string AssetRegistryRelativePath = ".codex-design/product/PUBLIC_LANDING_ASSET_REGISTRY.yaml";
    private readonly PublicCanonFileLoader _canon;
    private readonly PublicActionResolver _actions;

    public PublicLandingService(PublicCanonFileLoader canon, PublicActionResolver actions)
    {
        _canon = canon;
        _actions = actions;
    }

    public PublicLandingSurfaceDto LoadSurface()
    {
        var repoRoot = _canon.ResolveRepoRoot(ManifestRelativePath);
        var manifest = _canon.LoadRequiredYaml<PublicLandingManifestDocument>(ManifestRelativePath);
        var features = _canon.LoadRequiredYaml<PublicFeatureRegistryDocument>(FeatureRegistryRelativePath);
        var assets = _canon.LoadRequiredYaml<PublicAssetRegistryDocument>(AssetRegistryRelativePath);

        var surface = new PublicLandingSurfaceDto(
            Product: manifest.Product,
            Surface: manifest.Surface,
            Version: manifest.Version,
            Headline: RequireText(manifest.Headline, "headline"),
            Subhead: RequireText(manifest.Subhead, "subhead"),
            ProofLine: RequireText(manifest.ProofLine, "proof_line"),
            NoProviderNames: manifest.NoProviderNames,
            NoLtdNames: manifest.NoLtdNames,
            HeroCtas: (manifest.HeroCtas ?? new List<PublicLandingActionDocument>())
                .Select(static action => new PublicLandingActionDto(action.Label, action.Href, action.Emphasis))
                .ToArray(),
            GuestShellActions: (manifest.GuestShellActions ?? new List<PublicLandingActionDocument>())
                .Select(static action => new PublicLandingActionDto(action.Label, action.Href, action.Emphasis))
                .ToArray(),
            SecondaryHighlights: manifest.SecondaryHighlights ?? new List<string>(),
            ProductProofEyebrow: manifest.ProductProofEyebrow,
            ProductProofIntro: manifest.ProductProofIntro,
            ProductProofPrimaryLabel: manifest.ProductProofPrimaryLabel,
            ProductProofPrimaryHref: manifest.ProductProofPrimaryHref,
            ProductProofSecondaryLabel: manifest.ProductProofSecondaryLabel,
            ProductProofSecondaryHref: manifest.ProductProofSecondaryHref,
            ProductProofToplineLabel: manifest.ProductProofToplineLabel,
            ProductProofResultTitle: manifest.ProductProofResultTitle,
            ProductProofResultSummary: manifest.ProductProofResultSummary,
            ProductProofTrail: manifest.ProductProofTrail ?? new List<string>(),
            PublicRoutes: (manifest.PublicRoutes ?? new List<PublicLandingRouteDocument>())
                .Select(static route => new PublicLandingRouteDto(route.Path, route.Title, route.Audience, route.Purpose, route.RequiresAuth, route.GuestFallback, route.MustExist, route.PlaceholderAllowed, route.PlaceholderRequirements, route.VerificationMode, route.VerificationFile, route.VerificationPattern, route.VerificationPath))
                .ToArray(),
            AuthRoutes: (manifest.AuthRoutes ?? new List<PublicLandingRouteDocument>())
                .Select(static route => new PublicLandingRouteDto(route.Path, route.Title, route.Audience, route.Purpose, route.RequiresAuth, route.GuestFallback, route.MustExist, route.PlaceholderAllowed, route.PlaceholderRequirements, route.VerificationMode, route.VerificationFile, route.VerificationPattern, route.VerificationPath))
                .ToArray(),
            RegisteredRoutes: (manifest.RegisteredRoutes ?? new List<PublicLandingRouteDocument>())
                .Select(static route => new PublicLandingRouteDto(route.Path, route.Title, route.Audience, route.Purpose, route.RequiresAuth, route.GuestFallback, route.MustExist, route.PlaceholderAllowed, route.PlaceholderRequirements, route.VerificationMode, route.VerificationFile, route.VerificationPattern, route.VerificationPath))
                .ToArray(),
            Sections: (manifest.Sections ?? new List<PublicLandingSectionDocument>())
                .Select(static section => new PublicLandingSectionDto(section.Id, section.Eyebrow, section.Title, section.Intro, section.Audience, section.Route, section.AssetSlot))
                .ToArray(),
            RegisteredOverlays: (manifest.RegisteredOverlays ?? new List<PublicLandingOverlayDocument>())
                .Select(static overlay => new PublicLandingOverlayDto(overlay.Id, overlay.Path, overlay.Title, overlay.Summary))
                .ToArray(),
            Assets: (assets.Assets ?? new List<PublicLandingAssetDocument>())
                .Select(static asset => new PublicLandingAssetDto(
                    asset.AssetSlot,
                    asset.SectionId,
                    asset.MediaKind,
                    asset.PosterUrl,
                    asset.PosterAvifUrl,
                    asset.PosterWebpUrl,
                    asset.MobilePosterUrl,
                    asset.MobilePosterAvifUrl,
                    asset.MobilePosterWebpUrl,
                    asset.LoopUrl,
                    asset.Alt,
                    asset.Caption,
                    asset.MotionPolicy,
                    asset.FallbackStyle))
                .ToArray(),
            FooterCanonicalSource: manifest.FooterCanonicalSource,
            FooterGeneratedNote: manifest.FooterGeneratedNote,
            FeatureCards: (features.Cards ?? new List<PublicFeatureCardDocument>())
                .Select(static card => new PublicFeatureCardDto(
                    card.Id,
                    card.Bucket,
                    card.Title,
                    card.Summary,
                    card.Href,
                    card.Badge,
                    card.Audience,
                    card.ImageFamily,
                    card.AssetSlot ?? $"scene_{card.ImageFamily}",
                    card.CtaKind,
                    card.RenderMode,
                    card.DetailRoute,
                    card.FallbackRoute,
                    card.FallbackLabel,
                    card.GuestHref,
                    card.RegisteredHref,
                    card.ExternalOk,
                    card.SelfLinkAllowed,
                    card.ActionLabel,
                    card.DetailPrimaryHref,
                    card.DetailPrimaryLabel,
                    card.ProofNote,
                    card.Microproof,
                    card.Pain,
                    card.Payoff))
                .ToArray());

        ValidateSurface(surface, repoRoot);
        return surface;
    }

    public IReadOnlyList<PublicFeatureCardDto> CardsForBucket(PublicLandingSurfaceDto surface, string bucket)
        => surface.FeatureCards
            .Where(card => string.Equals(card.Bucket, bucket, StringComparison.Ordinal))
            .Where(CardVisibleOnPublicBucket)
            .ToArray();

    public PublicFeatureCardDto? FindCardByDetailRoute(PublicLandingSurfaceDto surface, string path)
        => surface.FeatureCards.FirstOrDefault(card =>
            !string.IsNullOrWhiteSpace(card.DetailRoute)
            && string.Equals(
                PublicRouteCatalog.NormalizeRoute(card.DetailRoute),
                PublicRouteCatalog.NormalizeRoute(path),
                StringComparison.OrdinalIgnoreCase));

    private void ValidateSurface(PublicLandingSurfaceDto surface, string repoRoot)
    {
        ValidateAssets(surface, repoRoot);
        ValidateSections(surface);

        var allowedRoutes = surface.PublicRoutes
            .Concat(surface.AuthRoutes)
            .Concat(surface.RegisteredRoutes)
            .Select(static route => PublicRouteCatalog.NormalizeRoute(route.Path))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (var action in surface.HeroCtas.Concat(surface.GuestShellActions))
        {
            ValidateRoute(action.Href, allowedRoutes, $"public action '{action.Label}'");
        }

        ValidateRoute(surface.ProductProofPrimaryHref, allowedRoutes, "product proof primary action");
        ValidateRoute(surface.ProductProofSecondaryHref, allowedRoutes, "product proof secondary action");

        foreach (var overlay in surface.RegisteredOverlays)
        {
            ValidateRoute(overlay.Path, allowedRoutes, $"registered overlay '{overlay.Id}'");
        }

        foreach (var section in surface.Sections)
        {
            ValidateRoute(section.Route, allowedRoutes, $"landing section '{section.Id}'");
        }

        foreach (var card in surface.FeatureCards)
        {
            _actions.ValidateActionableCard(card, allowedRoutes);
            ValidateCardProjection(card);
        }
    }

    private static void ValidateSections(PublicLandingSurfaceDto surface)
    {
        var sections = surface.Sections.ToDictionary(static section => section.Id, StringComparer.OrdinalIgnoreCase);
        foreach (var sectionId in new[]
                 {
                     "hero",
                     "product_proof",
                     "start_here",
                     "why_trust_it",
                     "choose_your_lane",
                     "whats_real_now",
                     "featured_artifacts",
                     "closing_cta"
                 })
        {
            if (!sections.TryGetValue(sectionId, out var section))
            {
                throw new InvalidOperationException($"required landing section missing: {sectionId}");
            }

            RequireText(section.Title, $"{sectionId}.title");
            RequireText(section.Eyebrow, $"{sectionId}.eyebrow");
            RequireText(section.Intro, $"{sectionId}.intro");
        }
    }

    private static void ValidateCardProjection(PublicFeatureCardDto card)
    {
        ValidateSelfLinkPolicy(card);
        ValidateDetailActionPolicy(card);
    }

    private static bool CardVisibleOnPublicBucket(PublicFeatureCardDto card)
    {
        if (string.IsNullOrWhiteSpace(card.Audience))
        {
            return true;
        }

        return card.Audience
            .Split(',', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries)
            .Any(static token => string.Equals(token, "public", StringComparison.OrdinalIgnoreCase));
    }

    private static void ValidateRoute(string? href, IReadOnlySet<string> allowedRoutes, string description)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            throw new InvalidOperationException($"{description} is missing an href.");
        }

        if (PublicUrlPolicy.IsExternalHref(href))
        {
            return;
        }

        var normalized = PublicRouteCatalog.NormalizeRoute(href);
        if (!PublicRouteCatalog.Contains(normalized, allowedRoutes))
        {
            throw new InvalidOperationException($"{description} points at missing route '{href}'.");
        }
    }

    private static void ValidateSelfLinkPolicy(PublicFeatureCardDto card)
    {
        if (card.SelfLinkAllowed)
        {
            return;
        }

        var hostRoute = card.Bucket switch
        {
            "start_here" => "/",
            "why_trust_it" => "/",
            "choose_your_lane" => "/",
            "supporting_reads" => "/what-is-chummer",
            "whats_real_now" => "/now",
            "coming_next" => "/horizons",
            "featured_artifacts" => "/artifacts",
            "participate" => "/participate",
            _ => null
        };

        if (string.IsNullOrWhiteSpace(hostRoute))
        {
            return;
        }

        foreach (var candidate in new[] { card.Href, card.DetailRoute, card.GuestHref, card.RegisteredHref, card.DetailPrimaryHref })
        {
            if (string.IsNullOrWhiteSpace(candidate) || PublicUrlPolicy.IsExternalHref(candidate))
            {
                continue;
            }

            if (candidate.Contains('#', StringComparison.Ordinal) || candidate.Contains('?', StringComparison.Ordinal))
            {
                continue;
            }

            if (string.Equals(PublicRouteCatalog.NormalizeRoute(candidate), hostRoute, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException($"public feature card '{card.Id}' points back to its own surface without self_link_allowed.");
            }
        }
    }

    private static void ValidateDetailActionPolicy(PublicFeatureCardDto card)
    {
        if (string.IsNullOrWhiteSpace(card.DetailRoute))
        {
            return;
        }

        if (!string.IsNullOrWhiteSpace(card.DetailPrimaryHref)
            && !string.IsNullOrWhiteSpace(card.FallbackRoute)
            && string.Equals(
                PublicRouteCatalog.NormalizeRoute(card.DetailPrimaryHref),
                PublicRouteCatalog.NormalizeRoute(card.FallbackRoute),
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"public feature card '{card.Id}' resolves the same detail primary and fallback route.");
        }
    }

    private static string RequireText(string? value, string name)
        => string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"required landing scalar missing: {name}")
            : value;

    private static void ValidateAssets(PublicLandingSurfaceDto surface, string repoRoot)
    {
        var webRoot = ResolveWebRoot(repoRoot);
        ValidateAsset(surface.Assets.FirstOrDefault(static asset => string.Equals(asset.AssetSlot, "section_hero", StringComparison.Ordinal)), "section_hero", webRoot, requireMobilePoster: true);
        if (surface.Assets.FirstOrDefault(static asset => string.Equals(asset.AssetSlot, "product_proof_ui", StringComparison.Ordinal)) is { } productProofAsset)
        {
            ValidateAsset(productProofAsset, "product_proof_ui", webRoot, requireMobilePoster: true);
        }

        foreach (var slot in surface.FeatureCards.Select(static card => card.AssetSlot).Distinct(StringComparer.Ordinal))
        {
            ValidateAsset(surface.Assets.FirstOrDefault(asset => string.Equals(asset.AssetSlot, slot, StringComparison.Ordinal)), slot, webRoot, requireMobilePoster: true);
        }
    }

    private static string ResolveWebRoot(string repoRoot)
    {
        foreach (var candidate in new[]
                 {
                     Path.Combine(repoRoot, "Chummer.Run.Api", "wwwroot"),
                     Path.Combine(repoRoot, "wwwroot")
                 })
        {
            if (Directory.Exists(candidate))
            {
                return Path.GetFullPath(candidate);
            }
        }

        throw new DirectoryNotFoundException($"Unable to resolve a public landing web root from '{repoRoot}'.");
    }

    private static void ValidateAsset(PublicLandingAssetDto? asset, string slot, string webRoot, bool requireMobilePoster)
    {
        if (asset is null)
        {
            throw new InvalidOperationException($"missing public landing asset slot: {slot}");
        }

        if (string.IsNullOrWhiteSpace(asset.PosterUrl))
        {
            throw new InvalidOperationException($"public landing asset '{slot}' is missing poster_url.");
        }

        if (requireMobilePoster && string.IsNullOrWhiteSpace(asset.MobilePosterUrl))
        {
            throw new InvalidOperationException($"public landing asset '{slot}' is missing mobile_poster_url.");
        }

        ValidateStaticAssetPath(asset.PosterUrl, webRoot, slot, "poster_url");
        ValidateStaticAssetPath(asset.PosterAvifUrl, webRoot, slot, "poster_avif_url");
        ValidateStaticAssetPath(asset.PosterWebpUrl, webRoot, slot, "poster_webp_url");
        ValidateStaticAssetPath(asset.MobilePosterUrl, webRoot, slot, "mobile_poster_url");
        ValidateStaticAssetPath(asset.MobilePosterAvifUrl, webRoot, slot, "mobile_poster_avif_url");
        ValidateStaticAssetPath(asset.MobilePosterWebpUrl, webRoot, slot, "mobile_poster_webp_url");
    }

    private static void ValidateStaticAssetPath(string? url, string webRoot, string slot, string fieldName)
    {
        if (string.IsNullOrWhiteSpace(url) || PublicUrlPolicy.IsExternalHref(url))
        {
            return;
        }

        var relative = url.Trim().TrimStart('/').Replace('/', Path.DirectorySeparatorChar);
        if (Path.GetExtension(relative).Equals(".svg", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"public landing asset '{slot}' uses SVG in {fieldName}: {url}. Raster delivery is required.");
        }

        var candidate = Path.GetFullPath(Path.Combine(webRoot, relative));
        if (!candidate.StartsWith(webRoot, StringComparison.Ordinal) || !File.Exists(candidate))
        {
            throw new InvalidOperationException($"public landing asset '{slot}' references missing {fieldName}: {url}");
        }
    }
}
