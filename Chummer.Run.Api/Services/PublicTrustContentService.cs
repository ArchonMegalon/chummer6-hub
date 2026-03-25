using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class PublicTrustContentService
{
    public TrustPageViewModel BuildHelpPage(SiteChromeViewModel chrome)
        => new(
            Chrome: chrome,
            Eyebrow: "Help",
            Heading: "How to get help without guessing",
            Intro: "Chummer is still early access, but the support path should still feel boring: where to ask, what is public, what stays private, and when guided contribution actually makes sense.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "First-party support",
                    "Start with the product surfaces first",
                    "Use the help, FAQ, account, privacy, terms, and contact pages before you fall through to deeper repo or community routes. The product front should answer normal customer questions without making you spelunk for them.",
                    new[]
                    {
                        "Help explains the support path.",
                        "FAQ answers the normal first questions.",
                        "Account handles sign-in, recovery, and linked-download follow-up.",
                        "Contact is where you go when the next step is still unclear."
                    }),
                new TrustPageSectionViewModel(
                    "Public feedback lane",
                    "Start with public feedback",
                    "Use the public path when you want to report a bug, flag confusing copy, or point at a feature that would make the product more useful.",
                    new[]
                    {
                        "Report a bug or rough edge.",
                        "Flag confusing public copy or onboarding friction.",
                        "Suggest a future lane that would help your table.",
                        "Check what works today first when you want the current customer-facing state."
                    }),
                new TrustPageSectionViewModel(
                    "Guided contribution lane",
                    "Use participation only when you want the deeper lane",
                    "Participation is the opt-in path for guided contribution help. It is temporary, review-safe, and additive on top of the normal public feedback path.",
                    new[]
                    {
                        "Participation is optional.",
                        "It does not bypass review.",
                        "You can stop or revoke later.",
                        "Recognition only appears after validated work lands."
                    }),
                new TrustPageSectionViewModel(
                    "Privacy and review",
                    "Normal help should stay low-drama",
                    "Public help should not require a public identity, and contributing should not force you into leaderboards or badges if you prefer to stay quiet.",
                    new[]
                    {
                        "Public recognition stays opt-in.",
                        "Private participation remains valid even when recognition exists.",
                        "The free baseline remains the default path.",
                        "Status and help pages should explain what happened without forcing repo spelunking."
                    }),
                new TrustPageSectionViewModel(
                    "What opens later",
                    "Some expensive lanes may open by invite first",
                    "That is a cost and safety posture, not a promise to lock the interesting parts away forever. The long-run intent is wider access once the lane becomes boring enough to operate safely.",
                    null)
            },
            Actions: BuildTrustActions(chrome.Authenticated));

    public FaqPageViewModel BuildFaqPage(SiteChromeViewModel chrome)
        => new(
            Chrome: chrome,
            Eyebrow: "FAQ",
            Heading: "Plain answers before you commit time",
            Intro: "The early-access pitch should still answer the normal questions directly: what is real, what is preview, how help works, and what deeper sources are for.",
            Sections: new[]
            {
                new FaqSectionViewModel(
                    "Using Chummer",
                    new[]
                    {
                        new FaqEntryViewModel("Can I actually use this now?", "Yes, with honest caveats. There are usable public surfaces and a real preview shelf, but several surfaces are still explicitly marked preview."),
                        new FaqEntryViewModel("Why would I trust it more than an opaque tool?", "Because the product is trying to make the number and the trail visible together: deterministic outcomes, readable receipts, and provenance instead of mystery math."),
                        new FaqEntryViewModel("What is preview versus available today?", "Available today means there is a real surface or build you can touch right now. Preview means the shape is usable but the support, release, or compatibility story is still moving.")
                    }),
                new FaqSectionViewModel(
                    "Participation and preview",
                    new[]
                    {
                        new FaqEntryViewModel("How can I help?", "Start with public feedback, bug reports, and feature suggestions. If you want to go further, the guided contribution lane exists as an opt-in path."),
                        new FaqEntryViewModel("Do I need to participate to help?", "No. The public feedback path remains the default path. Guided contribution is optional and additive, not the price of admission."),
                        new FaqEntryViewModel("Can I participate privately?", "Yes. Recognition should remain opt-in, and private participation should still be possible even when badges or leaderboards exist."),
                        new FaqEntryViewModel("Will some previews become free later?", "That is the long-run intent. Some lanes may start tighter while approvals, provenance, compatibility, or support costs are still unusually heavy.")
                    }),
                new FaqSectionViewModel(
                    "Deeper sources",
                    new[]
                    {
                        new FaqEntryViewModel("Where does the deeper plan live?", "In the published product materials and linked source trail. The public front should help you decide whether Chummer is for you before you ever need the deeper implementation view."),
                        new FaqEntryViewModel("Where does the code live?", "In the owning source repos. This front door exists so normal users do not have to reverse-engineer the product story from commit archaeology.")
                    })
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("See what works today", "/now", "primary"),
                new TrustPageActionViewModel("Open help", "/help", "secondary"),
                new TrustPageActionViewModel("Create account", "/signup?next=/home", "ghost")
            });

    public TrustPageViewModel BuildPrivacyPage(SiteChromeViewModel chrome)
        => new(
            Chrome: chrome,
            Eyebrow: "Privacy",
            Heading: "What Chummer stores, and what it does not",
            Intro: "The product should be honest about data handling. This page explains the practical early-access posture in plain language.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Hosted account data",
                    "Hub keeps the account record and your product preferences",
                    "The account keeps your basic profile, linked sign-in methods, recovery posture, update preferences, and participation record so the public and signed-in surfaces can stay coherent.",
                    new[]
                    {
                        "Display name and handle.",
                        "Linked sign-in and recovery posture.",
                        "Update and beta-interest preferences.",
                        "Participation status, badge state, and contribution receipts."
                    }),
                new TrustPageSectionViewModel(
                    "What stays out of Hub",
                    "Temporary contribution auth material does not belong here",
                    "Contribution authorization material stays on the execution host. The account keeps consent, state, and receipts; it does not keep raw provider auth caches.",
                    new[]
                    {
                        "No raw ChatGPT auth cache in Hub.",
                        "No temporary one-time-code secret storage in Hub.",
                        "No provider-credit or provider-secret storage in Hub."
                    }),
                new TrustPageSectionViewModel(
                    "Recognition and privacy",
                    "Recognition should not force publicity",
                    "Badges and leaderboards are recognition layers, not an excuse to make participation public by default. Private participation and private recognition settings remain valid.",
                    null),
                new TrustPageSectionViewModel(
                    "Early-access reality",
                    "This is the current product posture",
                    "This is a practical privacy statement for the current hosted product surface. It is meant to explain the live behavior honestly while the fuller legal and release posture continues to mature.",
                    null)
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("Open account", "/account", "primary"),
                new TrustPageActionViewModel("Read terms", "/terms", "secondary"),
                new TrustPageActionViewModel("Contact Chummer", "/contact", "ghost")
            });

    public TrustPageViewModel BuildTermsPage(SiteChromeViewModel chrome)
        => new(
            Chrome: chrome,
            Eyebrow: "Terms",
            Heading: "Preview terms in plain language",
            Intro: "This is not legal theater. It is the practical contract the hosted preview is trying to keep right now: what the product is promising, what may still move, and where support stops.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Preview posture",
                    "The product is real, but still early access",
                    "Chummer is trying to be usable and honest at the same time. Expect working surfaces, clear labels for preview lanes, and visible evidence when something is not fully settled yet.",
                    null),
                new TrustPageSectionViewModel(
                    "Account and participation",
                    "Accounts should be boring, participation should stay bounded",
                    "Normal sign-in should keep your access and preferences together. Participation remains opt-in, temporary, and review-safe. Authorization alone does not count as contribution credit.",
                    null),
                new TrustPageSectionViewModel(
                    "Downloads and updates",
                    "Installers are the preferred path when available",
                    "Installer builds are the product-default path. Manual archives remain available when needed, but they are the fallback path and should not be mistaken for the polished default experience.",
                    null),
                new TrustPageSectionViewModel(
                    "Support limits",
                    "Early access does not mean silent failure is acceptable",
                    "Support and legal posture are still maturing, but that is not a license for mystery behavior. The status, help, privacy, and contact pages should explain the current state in product language.",
                    null)
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("Open downloads", "/downloads", "primary"),
                new TrustPageActionViewModel("Read privacy", "/privacy", "secondary"),
                new TrustPageActionViewModel("Open help", "/help", "ghost")
            });

    public TrustPageViewModel BuildContactPage(SiteChromeViewModel chrome)
        => new(
            Chrome: chrome,
            Eyebrow: "Contact",
            Heading: "Where to send the right kind of problem",
            Intro: "A polished product should not make you guess where to go. Chummer is still early access, so the contact path is structured before it is fully staffed.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Account and sign-in trouble",
                    "Start from the account and help surfaces",
                    "Use the account page for sign-in, recovery, and linked-download questions first. Use the help surface when you need the current support path explained in product language.",
                    null),
                new TrustPageSectionViewModel(
                    "Product bugs and rough edges",
                    "Use the public issue tracker for reproducible public bugs",
                    "If something on the public surface is broken, confusing, or misleading and you can describe it cleanly, the public tracker keeps the problem visible instead of letting it disappear into side channels.",
                    null),
                new TrustPageSectionViewModel(
                    "Participation questions",
                    "Read the participation explainer before you open the deeper lane",
                    "The participation route should answer what the lane is for, what gets stored, and when recognition appears before you touch the wizard.",
                    null),
                new TrustPageSectionViewModel(
                    "What works today first",
                    "Check the customer state page when a failure looks systemic",
                    "If sign-in, downloads, or participation start failing across the board, check what works today first so you can tell the difference between an account issue and a host issue.",
                    null)
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("Open help", "/help", "primary"),
                new TrustPageActionViewModel("Open account", "/account", "secondary"),
                new TrustPageActionViewModel("Open public issue tracker", "https://github.com/ArchonMegalon/Chummer6/issues", "ghost")
            });

    private static IReadOnlyList<TrustPageActionViewModel> BuildTrustActions(bool authenticated)
        => authenticated
            ? new[]
            {
                new TrustPageActionViewModel("Open home", "/home", "primary"),
                new TrustPageActionViewModel("Open participate", "/participate", "secondary"),
                new TrustPageActionViewModel("Open account", "/account", "ghost")
            }
            : new[]
            {
                new TrustPageActionViewModel("Create account", "/signup?next=/home", "primary"),
                new TrustPageActionViewModel("See what works today", "/now", "secondary"),
                new TrustPageActionViewModel("Open participate", "/participate", "ghost")
            };
}
