using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class PublicTrustContentService
{
    private const string TrustContentRelativePath = ".codex-design/product/PUBLIC_TRUST_CONTENT.yaml";
    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;

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
            Eyebrow: page.Eyebrow,
            Heading: page.Heading,
            Intro: page.Intro,
            Sections: (page.Sections ?? new List<PublicFaqSectionDocument>())
                .Select(static section => new FaqSectionViewModel(
                    section.Title,
                    (section.Entries ?? new List<PublicFaqEntryDocument>())
                    .Select(static entry => new FaqEntryViewModel(entry.Question, entry.Answer))
                    .ToArray()))
                .ToArray(),
            Actions: BuildActions(page.Actions));
    }

    public TrustPageViewModel BuildPrivacyPage(SiteChromeViewModel chrome) => BuildTrustPage("privacy", chrome);

    public TrustPageViewModel BuildTermsPage(SiteChromeViewModel chrome) => BuildTrustPage("terms", chrome);

    public TrustPageViewModel BuildContactPage(SiteChromeViewModel chrome) => BuildTrustPage("contact", chrome);

    private TrustPageViewModel BuildTrustPage(string id, SiteChromeViewModel chrome)
    {
        var page = LoadDocument().TrustPages?.FirstOrDefault(candidate => string.Equals(candidate.Id, id, StringComparison.Ordinal))
                   ?? throw new InvalidOperationException($"public trust content is missing trust page '{id}'.");

        return new TrustPageViewModel(
            Chrome: chrome,
            Eyebrow: page.Eyebrow,
            Heading: page.Heading,
            Intro: page.Intro,
            Sections: (page.Sections ?? new List<PublicTrustSectionDocument>())
                .Select(static section => new TrustPageSectionViewModel(
                    section.Id,
                    section.Eyebrow,
                    section.Heading,
                    section.Body,
                    section.Bullets))
                .ToArray(),
            Actions: BuildActions(page.Actions));
    }

    private IReadOnlyList<TrustPageActionViewModel> BuildActions(IReadOnlyList<PublicTrustActionDocument>? actions)
        => (actions ?? new List<PublicTrustActionDocument>())
            .Select(action =>
            {
                _routes.ValidateRouteTarget(action.Href, $"trust action '{action.Label}'");
                return new TrustPageActionViewModel(action.Label, action.Href, action.Tone);
            })
            .ToArray();

    private PublicTrustContentDocument LoadDocument()
    {
        var document = _canon.LoadRequiredYaml<PublicTrustContentDocument>(TrustContentRelativePath);
        foreach (var page in document.TrustPages ?? new List<PublicTrustPageDocument>())
        {
            BuildActions(page.Actions);
        }

        foreach (var page in document.FaqPages ?? new List<PublicFaqPageDocument>())
        {
            BuildActions(page.Actions);
        }

        return document;
    }
}
