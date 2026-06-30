using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class PublicTrustContentService
{
    private const string TrustContentRelativePath = ".codex-design/product/PUBLIC_TRUST_CONTENT.yaml";
    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;
    private readonly object _documentLock = new();
    private PublicTrustContentDocument? _cachedDocument;

    public PublicTrustContentService(PublicCanonFileLoader canon, PublicRouteCatalogService routes)
    {
        _canon = canon;
        _routes = routes;
    }

    public TrustPageViewModel BuildHelpPage(SiteChromeViewModel chrome) => BuildTrustPage("help", chrome);

    public FaqPageViewModel BuildFaqPage(SiteChromeViewModel chrome)
    {
        var page = LoadDocument().FaqPages?.FirstOrDefault(static candidate => string.Equals(candidate.Id, "faq", StringComparison.Ordinal))
                   ?? throw new InvalidOperationException("public trust content is missing faq page.");

        return new FaqPageViewModel(
            Chrome: chrome,
            Eyebrow: RequireText(page.Eyebrow, "faq page eyebrow"),
            Heading: RequireText(page.Heading, "faq page heading"),
            Intro: RequireText(page.Intro, "faq page intro"),
            Sections: (page.Sections ?? new List<PublicFaqSectionDocument>())
                .Select(section => new FaqSectionViewModel(
                    RequireText(section.Title, "faq section title"),
                    (section.Entries ?? new List<PublicFaqEntryDocument>())
                    .Select(entry => new FaqEntryViewModel(
                        RequireText(entry.Question, "faq entry question"),
                        RequireText(entry.Answer, "faq entry answer")))
                    .ToArray()))
                .ToArray(),
            Actions: BuildActions(page.Actions, chrome.Authenticated));
    }

    public TrustPageViewModel BuildPrivacyPage(SiteChromeViewModel chrome) => BuildTrustPage("privacy", chrome);

    public TrustPageViewModel BuildTermsPage(SiteChromeViewModel chrome) => BuildTrustPage("terms", chrome);

    public TrustPageViewModel BuildContactPage(SiteChromeViewModel chrome) => BuildTrustPage("contact", chrome);

    private TrustPageViewModel BuildTrustPage(string id, SiteChromeViewModel chrome)
    {
        var page = LoadDocument().TrustPages?.FirstOrDefault(candidate => string.Equals(candidate.Id, id, StringComparison.Ordinal))
                   ?? throw new InvalidOperationException($"public trust content is missing trust page '{id}'.");

        return new TrustPageViewModel(
            PageId: id,
            Chrome: chrome,
            Eyebrow: RequireText(page.Eyebrow, $"trust page '{id}' eyebrow"),
            Heading: RequireText(page.Heading, $"trust page '{id}' heading"),
            Intro: RequireText(page.Intro, $"trust page '{id}' intro"),
            Sections: (page.Sections ?? new List<PublicTrustSectionDocument>())
                .Select(section => new TrustPageSectionViewModel(
                    RequireText(section.Id, $"trust page '{id}' section id"),
                    RequireText(section.Eyebrow, $"trust page '{id}' section eyebrow"),
                    RequireText(section.Heading, $"trust page '{id}' section heading"),
                    RequireText(section.Body, $"trust page '{id}' section body"),
                    section.Bullets))
                .ToArray(),
            Actions: BuildActions(page.Actions, chrome.Authenticated),
            EffectiveDate: page.EffectiveDate,
            UpdatedDate: page.UpdatedDate,
            SummaryPoints: page.SummaryPoints);
    }

    private IReadOnlyList<TrustPageActionViewModel> BuildActions(IReadOnlyList<PublicTrustActionDocument>? actions, bool authenticated)
        => (actions ?? new List<PublicTrustActionDocument>())
            .Select(action =>
            {
                var label = RequireText(action.Label, "trust action label");
                var href = RequireText(action.Href, $"trust action '{label}' href");
                if (!authenticated)
                {
                    var normalized = PublicRouteCatalog.NormalizeRoute(href);
                    if (string.Equals(normalized, "/account", StringComparison.OrdinalIgnoreCase)
                        || string.Equals(normalized, "/home", StringComparison.OrdinalIgnoreCase))
                    {
                        href = $"/signup?next={Uri.EscapeDataString(action.Href)}";
                        label = "Claim your copy";
                    }
                }

                _routes.ValidateRouteTarget(href, $"trust action '{label}'");
                return new TrustPageActionViewModel(label, href, action.Tone);
            })
            .ToArray();

    private PublicTrustContentDocument LoadDocument()
    {
        lock (_documentLock)
        {
            if (_cachedDocument is not null)
            {
                return _cachedDocument;
            }
        }

        var document = _canon.LoadRequiredYaml<PublicTrustContentDocument>(TrustContentRelativePath);
        ValidateDocument(document);

        lock (_documentLock)
        {
            _cachedDocument ??= document;
            return _cachedDocument;
        }
    }

    private void ValidateDocument(PublicTrustContentDocument document)
    {
        foreach (var page in document.TrustPages ?? new List<PublicTrustPageDocument>())
        {
            BuildActions(page.Actions, authenticated: true);
        }

        foreach (var page in document.FaqPages ?? new List<PublicFaqPageDocument>())
        {
            BuildActions(page.Actions, authenticated: true);
        }
    }

    private static string RequireText(string? value, string description)
        => string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"{description} is missing required text.")
            : value;
}
