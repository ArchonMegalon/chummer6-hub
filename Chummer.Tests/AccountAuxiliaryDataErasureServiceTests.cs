using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountAuxiliaryDataErasureServiceTests
{
    private static readonly DateTimeOffset Baseline = new(2026, 8, 12, 12, 0, 0, TimeSpan.Zero);

    [Fact]
    public void Erase_removes_account_data_from_auxiliary_first_party_stores()
    {
        using Fixture fixture = new();
        fixture.Brilliant.Members.Add(new BrilliantDirectoriesMemberSnapshotDto(
            "user-delete", "member-1", "delete@example.invalid", "supporter", "Supporter", "active", true, Baseline, Baseline));
        fixture.MyFirstBook.Entries.Add(new MyFirstBookUsageLedgerEntry("user-delete", Baseline, 3, Baseline));
        fixture.HorizonUsage.Entries.Add(new HorizonArtifactUsageLedgerEntry(
            "user-delete", "origin-dossier", "book", "epub", "month", Baseline, 1, Baseline));
        fixture.OriginReservations.Entries.Add(new OriginDossierProviderCreditReservationLedgerEntry(
            "reservation-1", "user-delete", "project-1", "provider", "account", 2, "reserved", Baseline, Baseline));
        fixture.ArtifactRequests.Receipts.Add(new HorizonArtifactRequestReceipt(
            "request-1", "queued", "origin-dossier", "book", "epub", "Book", "book", "source",
            "user-delete", "private", true, [], Baseline, true));
        fixture.PayFunnels.Intents.Add(new PaymentIntentDto(
            "intent-1", "user-delete", "supporter", 1000, "EUR", "created", true, "https://example.invalid", Baseline));
        fixture.InstallSnapshots.SnapshotsByKey["subject:subject-delete|workspace-1"] =
            new InstallLinkedWorkspaceSnapshotRecord(
                "subject:subject-delete", "workspace-1", "sr5", "chummer", 1, "character", "private payload",
                Baseline, "installation-1", "Name", "Alias", "Human", "priority", "6", "6", 0, 0, true);
        fixture.InstallLinking.PersonalizedInstallScriptsById["script-1"] = new PersonalizedInstallScriptLinkDto(
            "script-1", "artifact-1", ["artifact-1"], "windows", Baseline, Baseline.AddHours(1),
            PersonalizedInstallScriptStates.Pending, "user-delete", "subject-delete", "private script", new string('a', 64));
        fixture.Venues.VenuesBySessionKey["venue-key"] = new GmSessionVenueProjection(
            "venue-1", "campaign-1", "session-1", "user-delete", "manual", "link", "private", null, null, null,
            "ready", Baseline, null, "private", "confirmed", Baseline, Baseline);
        fixture.VideoFoundry.FacesById["face-1"] = new FaceAssetProjection(
            "face-1", "user-delete", "workspace-1", "campaign-1", "Runner", "human", [], "upload", "private", [],
            "confirmed", false, "object-1", "thumb-1", null, Baseline, Baseline);
        fixture.PromptFoundry.DraftsById["draft-1"] = new PromptFoundryDraftProjection(
            "draft-1", "template-1", "campaign-1", "group-1", "user-delete", null, "local", "private prompt", null,
            "negative", [], [], "passed", null, 1, "draft", Baseline, Baseline, null);

        AccountAuxiliaryDataErasureResult result = fixture.Service.Erase("user-delete", "subject-delete");

        Assert.True(result.RecordsRemoved >= 11);
        Assert.Equal(13, result.RecordsRemovedByComponent.Count);
        Assert.Empty(fixture.Brilliant.Members);
        Assert.Empty(fixture.MyFirstBook.Entries);
        Assert.Empty(fixture.HorizonUsage.Entries);
        Assert.Empty(fixture.OriginReservations.Entries);
        Assert.Empty(fixture.ArtifactRequests.Receipts);
        Assert.Empty(fixture.PayFunnels.Intents);
        Assert.Empty(fixture.InstallSnapshots.SnapshotsByKey);
        Assert.Empty(fixture.InstallLinking.PersonalizedInstallScriptsById);
        Assert.Empty(fixture.Venues.VenuesBySessionKey);
        Assert.Empty(fixture.VideoFoundry.FacesById);
        Assert.Empty(fixture.PromptFoundry.DraftsById);

        AccountAuxiliaryDataErasureResult repeated = fixture.Service.Erase("user-delete", "subject-delete");
        Assert.Equal(0, repeated.RecordsRemoved);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(
            Path.GetTempPath(),
            "chummer-auxiliary-erasure-tests",
            Guid.NewGuid().ToString("N"));

        public Fixture()
        {
            Directory.CreateDirectory(_directory);
            var values = new Dictionary<string, string?>
            {
                ["ASPNETCORE_ENVIRONMENT"] = "Testing",
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = PathFor("brilliant.json"),
                ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = PathFor("myfirstbook.json"),
                ["CHUMMER_HORIZON_ARTIFACT_USAGE_STORE_PATH"] = PathFor("horizon-usage.json"),
                ["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORE_PATH"] = PathFor("origin-reservations.json"),
                ["CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH"] = PathFor("artifact-requests.json"),
                ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = PathFor("payfunnels.json"),
                ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = PathFor("install-snapshots.json"),
                ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = PathFor("install-linking.json"),
                ["CHUMMER_GM_SESSION_VENUE_STORE_PATH"] = PathFor("venues.json"),
                ["CHUMMER_GM_SESSION_VIDEO_FOUNDRY_STORE_PATH"] = PathFor("video-foundry.json"),
                ["CHUMMER_PROMPT_FOUNDRY_STORE_PATH"] = PathFor("prompt-foundry.json"),
                ["CHUMMER_KARMA_FORGE_STORE_PATH"] = PathFor("karma-forge.json"),
                ["CHUMMER_ORIGIN_DOSSIER_PUBLICATION_INDEX_PATH"] = PathFor("origin-publications.json")
            };
            Configuration = new ConfigurationBuilder().AddInMemoryCollection(values).Build();
            Brilliant = new BrilliantDirectoriesBillingStore(Configuration);
            MyFirstBook = new MyFirstBookUsageStore(Configuration);
            HorizonUsage = new HorizonArtifactUsageStore(Configuration);
            OriginReservations = new OriginDossierProviderCreditReservationStore(Configuration);
            ArtifactRequests = new HorizonArtifactRequestReceiptStore(Configuration);
            PayFunnels = new PayFunnelsBillingStore(Configuration);
            InstallSnapshots = new InstallLinkedWorkspaceSnapshotStore(Configuration);
            InstallLinking = new InstallLinkingStore(
                Configuration,
                new EphemeralDataProtectionProvider(),
                NullLogger<InstallLinkingStore>.Instance);
            Venues = new GmSessionVenueStore(Configuration);
            VideoFoundry = new GmSessionVideoFoundryStore(Configuration);
            PromptFoundry = new PromptFoundryStore(Configuration);
            KarmaForge = new KarmaForgeStore(Configuration, NullLogger<KarmaForgeStore>.Instance);
            OriginDossiers = new OriginDossierPublicationService(
                Configuration,
                NullLogger<OriginDossierPublicationService>.Instance);
            Service = new AccountAuxiliaryDataErasureService(
                Brilliant,
                MyFirstBook,
                HorizonUsage,
                OriginReservations,
                ArtifactRequests,
                PayFunnels,
                InstallSnapshots,
                InstallLinking,
                Venues,
                VideoFoundry,
                PromptFoundry,
                KarmaForge,
                OriginDossiers);
        }

        public IConfiguration Configuration { get; }
        public BrilliantDirectoriesBillingStore Brilliant { get; }
        public MyFirstBookUsageStore MyFirstBook { get; }
        public HorizonArtifactUsageStore HorizonUsage { get; }
        public OriginDossierProviderCreditReservationStore OriginReservations { get; }
        public HorizonArtifactRequestReceiptStore ArtifactRequests { get; }
        public PayFunnelsBillingStore PayFunnels { get; }
        public InstallLinkedWorkspaceSnapshotStore InstallSnapshots { get; }
        public InstallLinkingStore InstallLinking { get; }
        public GmSessionVenueStore Venues { get; }
        public GmSessionVideoFoundryStore VideoFoundry { get; }
        public PromptFoundryStore PromptFoundry { get; }
        public KarmaForgeStore KarmaForge { get; }
        public OriginDossierPublicationService OriginDossiers { get; }
        public AccountAuxiliaryDataErasureService Service { get; }

        private string PathFor(string name) => Path.Combine(_directory, name);

        public void Dispose()
        {
            InstallLinking.Dispose();
            try
            {
                Directory.Delete(_directory, recursive: true);
            }
            catch
            {
                // Best-effort cleanup for test temp files.
            }
        }
    }
}
