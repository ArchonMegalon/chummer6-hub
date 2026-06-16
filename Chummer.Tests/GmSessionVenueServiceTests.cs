using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Text;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class GmSessionVenueServiceTests
{
    [Fact]
    public void Manual_link_mode_accepts_verified_behuman_room_url_and_logs_receipt()
    {
        using TestVenueHarness harness = new();

        VenueLinkReceiptProjection receipt = harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-1",
            new ManualVenueLinkRequest(
                VenueUrl: "https://behuman.online/rooms/test-room",
                Visibility: "private_campaign"));

        GmSessionVenueProjection venue = harness.Service.GetVenue("user-1", "campaign-1", "session-1");

        Assert.True(receipt.LinkValidated);
        Assert.Equal("behuman", venue.Provider);
        Assert.Equal("manual_link_mode", venue.Mode);
        Assert.Equal("manual_link_added", venue.VenueStatus);
        Assert.Equal("private_campaign", venue.Visibility);
        Assert.Equal("pass", venue.PrivacyStatus);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal("venue_link", receipt.Envelope!.ReceiptKind);
        Assert.Equal("community.gm_session_venue", receipt.Envelope.OwnerScope);
    }

    [Fact]
    public void Manual_link_mode_rejects_unknown_domains()
    {
        using TestVenueHarness harness = new();

        ArgumentException ex = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-2",
            new ManualVenueLinkRequest("https://evil.example/room")));

        Assert.Contains("allowed BeHuman domain", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Manual_link_mode_rejects_suspicious_query_payloads()
    {
        using TestVenueHarness harness = new();

        ArgumentException ex = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-query",
            new ManualVenueLinkRequest("https://behuman.online/rooms/test-room?access_token=secret")));

        Assert.Contains("suspicious query payload", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Manual_link_mode_rejects_fragments_and_embedded_credentials()
    {
        using TestVenueHarness harness = new();

        ArgumentException fragment = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-fragment",
            new ManualVenueLinkRequest("https://behuman.online/rooms/test-room#private")));
        Assert.Contains("fragments", fragment.Message, StringComparison.OrdinalIgnoreCase);

        ArgumentException credentials = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-creds",
            new ManualVenueLinkRequest("https://user:pass@behuman.online/rooms/test-room")));
        Assert.Contains("embedded credentials", credentials.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Manual_link_mode_rejects_shortened_domains()
    {
        using TestVenueHarness harness = new(new Dictionary<string, string?>
        {
            ["Community:BeHuman:AllowedDomains"] = "behuman.online,bit.ly"
        });

        ArgumentException ex = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-shortener",
            new ManualVenueLinkRequest("https://bit.ly/test-room")));

        Assert.Contains("shortened domain", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Manual_link_mode_rejects_provider_email_invites_without_consent()
    {
        using TestVenueHarness harness = new();

        ArgumentException ex = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-consent",
            new ManualVenueLinkRequest(
                VenueUrl: "https://behuman.online/rooms/test-room",
                ProviderDirectEmailInvites: true,
                ConsentToShareAttendeeEmails: false)));

        Assert.Contains("explicit consent", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Manual_link_mode_rejects_invalid_schedule_ranges()
    {
        using TestVenueHarness harness = new();
        DateTimeOffset start = DateTimeOffset.UtcNow.AddDays(1);
        DateTimeOffset end = start.AddHours(-1);

        ArgumentException ex = Assert.Throws<ArgumentException>(() => harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-range",
            new ManualVenueLinkRequest(
                VenueUrl: "https://behuman.online/rooms/test-room",
                ScheduledStartUtc: start,
                ScheduledEndUtc: end)));

        Assert.Contains("scheduled_end_utc", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Create_mode_stays_honestly_disabled_without_verified_transport_base_url()
    {
        string root = Path.Combine(Path.GetTempPath(), $"behuman-gm-venue-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        string receiptPath = Path.Combine(root, "behuman-verification.yaml");
        File.WriteAllText(receiptPath, "provider: behuman.online\nverified: true\n", System.Text.Encoding.UTF8);

        try
        {
            using TestVenueHarness harness = new(new Dictionary<string, string?>
            {
                ["Community:BeHuman:Enabled"] = "true",
                ["Community:BeHuman:Mode"] = "api_verified",
                ["Community:BeHuman:ProviderVerificationReceiptPath"] = receiptPath,
                ["BEHUMAN_API_KEY"] = "test-secret"
            });

            InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => harness.Service.CreateBeHumanVenue(
                "user-1",
                "campaign-1",
                "session-3",
                new CreateBeHumanVenueRequest("Friday Night One-Shot", DateTimeOffset.UtcNow.AddDays(1))));

            Assert.Contains("base URL", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void Create_mode_stays_unavailable_while_adapter_is_manual_only()
    {
        string root = Path.Combine(Path.GetTempPath(), $"behuman-gm-venue-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        string receiptPath = Path.Combine(root, "behuman-verification.yaml");
        File.WriteAllText(receiptPath, "provider: behuman.online\nverified: true\n", Encoding.UTF8);

        try
        {
            using TestVenueHarness harness = new(new Dictionary<string, string?>
            {
                ["Community:BeHuman:Enabled"] = "true",
                ["Community:BeHuman:Mode"] = "manual",
                ["Community:BeHuman:ProviderVerificationReceiptPath"] = receiptPath,
                ["Community:BeHuman:VenueApiBaseUrl"] = "https://behuman.online",
                ["BEHUMAN_API_KEY"] = "test-secret"
            });

            InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => harness.Service.CreateBeHumanVenue(
                "user-1",
                "campaign-1",
                "session-manual-create",
                new CreateBeHumanVenueRequest("Manual Mode Test", DateTimeOffset.UtcNow.AddDays(1))));

            Assert.Contains("manual-link mode", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void Create_mode_creates_verified_provider_room_and_logs_receipt()
    {
        string root = Path.Combine(Path.GetTempPath(), $"behuman-gm-venue-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        string receiptPath = Path.Combine(root, "behuman-verification.yaml");
        File.WriteAllText(receiptPath, "provider: behuman.online\nverified: true\n", Encoding.UTF8);

        try
        {
            using TestVenueHarness harness = new(new Dictionary<string, string?>
            {
                ["Community:BeHuman:Enabled"] = "true",
                ["Community:BeHuman:Mode"] = "api_verified",
                ["Community:BeHuman:ProviderVerificationReceiptPath"] = receiptPath,
                ["Community:BeHuman:VenueApiBaseUrl"] = "https://behuman.online",
                ["BEHUMAN_API_KEY"] = "test-secret"
            }, new StaticHttpClientFactory(new HttpClient(new StubHandler(request =>
            {
                Assert.Equal(HttpMethod.Post, request.Method);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("""{"venue_id":"bh-room-1","event_url":"https://behuman.online/events/bh-room-1","room_url":"https://behuman.online/rooms/bh-room-1","privacy_status":"pass","capacity":12}""", Encoding.UTF8, "application/json")
                };
            }))));

            VenueCreatedReceiptProjection receipt = harness.Service.CreateBeHumanVenue(
                "user-1",
                "campaign-1",
                "session-3",
                new CreateBeHumanVenueRequest("Friday Night One-Shot", DateTimeOffset.UtcNow.AddDays(1), RegistrationCapacity: 12));

            GmSessionVenueProjection venue = harness.Service.GetVenue("user-1", "campaign-1", "session-3");

            Assert.Equal("bh-room-1", receipt.ProviderEventId);
            Assert.Equal("adapter_create_mode", receipt.AdapterMode);
            Assert.Equal("provider_created", venue.VenueStatus);
            Assert.Equal("adapter_create_mode", venue.Mode);
            Assert.Equal("https://behuman.online/rooms/bh-room-1", venue.ProviderRoomUrl);
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void Venues_are_scoped_per_owner_account()
    {
        using TestVenueHarness harness = new();

        harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-shared",
            new ManualVenueLinkRequest("https://behuman.online/rooms/user-one"));

        GmSessionVenueProjection otherOwnerView = harness.Service.GetVenue("user-2", "campaign-1", "session-shared");

        Assert.Equal("none", otherOwnerView.Provider);
        Assert.Equal("not_configured", otherOwnerView.VenueStatus);
        Assert.Null(otherOwnerView.ProviderRoomUrl);
    }

    [Fact]
    public void Campaign_members_can_view_but_only_gm_roles_can_manage()
    {
        using TestVenueHarness harness = new();

        GmSessionVenueProjection venue = harness.Service.GetVenue("user-2", "campaign-1", "session-member-view");
        Assert.Equal("not_configured", venue.VenueStatus);

        CommunityAccessDeniedException ex = Assert.Throws<CommunityAccessDeniedException>(() => harness.Service.AddManualVenueLink(
            "user-2",
            "campaign-1",
            "session-member-view",
            new ManualVenueLinkRequest("https://behuman.online/rooms/member-attempt")));

        Assert.Contains("must be an owner", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Closeout_creates_receipt_without_silent_attendance_import()
    {
        using TestVenueHarness harness = new();
        harness.Service.AddManualVenueLink(
            "user-1",
            "campaign-1",
            "session-4",
            new ManualVenueLinkRequest("https://behuman.online/rooms/test-room"));

        SessionVenueCloseoutReceiptProjection receipt = harness.Service.CloseVenue(
            "user-1",
            "campaign-1",
            "session-4",
            new SessionVenueCloseoutRequest(SyncAttendance: true, ConsentToImportAttendance: false, RecapStatus: "public_safe"));

        GmSessionVenueProjection venue = harness.Service.GetVenue("user-1", "campaign-1", "session-4");

        Assert.Equal("missing", receipt.AttendanceSyncStatus);
        Assert.Equal("public_safe", receipt.RecapStatus);
        Assert.Equal("closed", venue.VenueStatus);
    }

    [Fact]
    public void Closeout_syncs_attendance_for_provider_created_venues_after_consent()
    {
        string root = Path.Combine(Path.GetTempPath(), $"behuman-gm-venue-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        string receiptPath = Path.Combine(root, "behuman-verification.yaml");
        File.WriteAllText(receiptPath, "provider: behuman.online\nverified: true\n", Encoding.UTF8);

        try
        {
            using TestVenueHarness harness = new(new Dictionary<string, string?>
            {
                ["Community:BeHuman:Enabled"] = "true",
                ["Community:BeHuman:Mode"] = "api_verified",
                ["Community:BeHuman:ProviderVerificationReceiptPath"] = receiptPath,
                ["Community:BeHuman:VenueApiBaseUrl"] = "https://behuman.online",
                ["BEHUMAN_API_KEY"] = "test-secret"
            }, new StaticHttpClientFactory(new HttpClient(new StubHandler(request =>
            {
                if (request.Method == HttpMethod.Post)
                {
                    return new HttpResponseMessage(HttpStatusCode.OK)
                    {
                        Content = new StringContent("""{"venue_id":"bh-room-2","event_url":"https://behuman.online/events/bh-room-2","room_url":"https://behuman.online/rooms/bh-room-2","privacy_status":"pass"}""", Encoding.UTF8, "application/json")
                    };
                }

                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("""{"attendee_count":5}""", Encoding.UTF8, "application/json")
                };
            }))));

            harness.Service.CreateBeHumanVenue(
                "user-1",
                "campaign-1",
                "session-sync",
                new CreateBeHumanVenueRequest("Saturday Run", DateTimeOffset.UtcNow.AddDays(1)));

            SessionVenueCloseoutReceiptProjection receipt = harness.Service.CloseVenue(
                "user-1",
                "campaign-1",
                "session-sync",
                new SessionVenueCloseoutRequest(SyncAttendance: true, ConsentToImportAttendance: true));

            Assert.Equal("complete", receipt.AttendanceSyncStatus);
            Assert.Equal(5, receipt.AttendeeCount);
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    [Fact]
    public void Closeout_requires_existing_configured_venue()
    {
        using TestVenueHarness harness = new();

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => harness.Service.CloseVenue(
            "user-1",
            "campaign-1",
            "missing-session",
            new SessionVenueCloseoutRequest()));

        Assert.Contains("not configured", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class TestVenueHarness : IDisposable
    {
        private readonly string _root;

        public TestVenueHarness(IDictionary<string, string?>? extra = null, IHttpClientFactory? httpClientFactory = null)
        {
            _root = Path.Combine(Path.GetTempPath(), $"gm-session-venue-store-{Guid.NewGuid():N}");
            Directory.CreateDirectory(_root);

            Dictionary<string, string?> values = new(StringComparer.OrdinalIgnoreCase)
            {
                ["CHUMMER_GM_SESSION_VENUE_STORE_PATH"] = Path.Combine(_root, "gm-session-venues.json"),
                ["Community:BeHuman:AllowedDomains"] = "behuman.online"
            };
            if (extra is not null)
            {
                foreach ((string key, string? value) in extra)
                {
                    values[key] = value;
                }
            }

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(values)
                .Build();

            CommunityStore communityStore = new(configuration, Microsoft.Extensions.Logging.Abstractions.NullLogger<CommunityStore>.Instance);
            SeedCampaignMembership(communityStore);
            Store = new GmSessionVenueStore(configuration);
            IHttpClientFactory factory = httpClientFactory ?? new StaticHttpClientFactory(new HttpClient(new StubHandler(_ =>
                new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("""{}""", Encoding.UTF8, "application/json")
                })));
            BeHumanEventAdapterPostureService posture = new(configuration);
            IGmSessionVenueAdapter adapter = new BeHumanGmSessionVenueAdapter(factory, configuration, posture);
            Service = new GmSessionVenueService(Store, posture, adapter, configuration, communityStore);
        }

        public GmSessionVenueStore Store { get; }
        public GmSessionVenueService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, true);
            }
        }

        private static void SeedCampaignMembership(CommunityStore communityStore)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            HubUserDto userOne = new(
                "user-1",
                "subject-1",
                "User One",
                "user-one",
                "private",
                "UTC",
                "AT",
                [],
                ["group-1"],
                now,
                now);
            HubUserDto userTwo = new(
                "user-2",
                "subject-2",
                "User Two",
                "user-two",
                "private",
                "UTC",
                "AT",
                [],
                ["group-1"],
                now,
                now);
            GroupDto group = new(
                "group-1",
                "campaign",
                "Campaign Group",
                "private",
                "user-1",
                ["can_manage_members"],
                [
                    new GroupMembershipDto("mbr-1", "group-1", "user-1", "gm", now),
                    new GroupMembershipDto("mbr-2", "group-1", "user-2", "member", now)
                ],
                now,
                now);
            BoostCampaignDto campaign = new(
                "campaign-1",
                "group-1",
                "project-1",
                "Campaign One",
                "active",
                now);

            lock (communityStore.Gate)
            {
                communityStore.UsersById[userOne.UserId] = userOne;
                communityStore.UsersById[userTwo.UserId] = userTwo;
                communityStore.GroupsById[group.GroupId] = group;
                communityStore.CampaignsById[campaign.CampaignId] = campaign;
            }
        }
    }

    private sealed class StaticHttpClientFactory : IHttpClientFactory
    {
        private readonly HttpClient _client;

        public StaticHttpClientFactory(HttpClient client)
        {
            _client = client;
        }

        public HttpClient CreateClient(string name) => _client;
    }

    private sealed class StubHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> _handler;

        public StubHandler(Func<HttpRequestMessage, HttpResponseMessage> handler)
        {
            _handler = handler;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(_handler(request));
    }
}
