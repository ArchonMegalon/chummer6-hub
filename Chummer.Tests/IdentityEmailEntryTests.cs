using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class IdentityEmailEntryTests : IDisposable
{
    private const string Email = "runner@example.invalid";
    private static readonly string SubjectId = IdentitySubjectDerivation.FromEmail(Email);
    private readonly string _root = Path.Combine(Path.GetTempPath(), "identity-email-entry-" + Guid.NewGuid().ToString("N"));
    private string StorePath => Path.Combine(_root, "identity.json");

    private IConfiguration Configuration() => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["ASPNETCORE_ENVIRONMENT"] = "Production",
        ["CHUMMER_IDENTITY_STORE_PATH"] = StorePath,
        ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(_root, "delivery.json"),
        ["IDENTITY_EMAIL_START_ENABLED"] = "true",
        ["IDENTITY_EMAIL_START_MIN_SECONDS_BETWEEN_RECIPIENT_ATTEMPTS"] = "0",
        ["IDENTITY_EMAIL_START_MAX_ATTEMPTS_PER_RECIPIENT_PER_WINDOW"] = "20"
    }).Build();

    private IdentityAccessService Service(IIdentityEmailDeliveryService mail) =>
        new(Configuration(), NullLogger<IdentityAccessService>.Instance, mail);

    private static void Seed(IdentityAccessService service, string name = "Original Name") =>
        service.IssueSession(new(SubjectId, name, Email, ["player", "gm"]));

    // Compare all subject fields, including roles and UpdatedAtUtc, across reloads.
    private static string Subject(IdentityAccessService service) => JsonSerializer.Serialize(service.GetSubject(SubjectId));

    [Theory]
    [InlineData("email_delivery_unavailable")]
    [InlineData("email_delivery_failed")]
    [InlineData("throw")]
    public void Failed_or_unknown_delivery_and_repeated_starts_never_edit_an_existing_subject(string mode)
    {
        var mail = new CapturingMail(mode);
        var service = Service(mail);
        Seed(service);
        string original = Subject(service);
        mail.BeforeDelivery = () => Assert.Equal(original, Subject(service));

        for (int attempt = 0; attempt < 2; attempt++)
        {
            var request = new EmailAuthStartRequest(Email, "Unverified " + attempt);
            if (mode == "throw")
                Assert.Throws<IOException>(() => service.StartEmailEntry(request));
            else
                Assert.Empty(service.StartEmailEntry(request).TicketId);
            Assert.Equal(original, Subject(service));
            service = Service(mail);
            Assert.Equal(original, Subject(service));
        }

        if (mode == "throw")
        {
            // Delivery outcome is unknown: preserve existing pending-ticket behavior.
            Assert.Equal("Original Name", service.CompleteEmailEntry(new(mail.Tickets[0])).DisplayName);
        }
        else
        {
            foreach (string ticket in mail.Tickets)
                Assert.Throws<KeyNotFoundException>(() => service.CompleteEmailEntry(new(ticket)));
        }
        Assert.Equal(original, Subject(Service(mail)));
    }

    [Fact]
    public void Disabled_production_mail_does_not_edit_subject_or_expose_a_ticket()
    {
        var configuration = Configuration();
        using var client = new HttpClient(new RejectNetwork());
        var mail = new IdentityEmailDeliveryService(configuration, NullLogger<IdentityEmailDeliveryService>.Instance, client);
        var service = Service(mail);
        Seed(service);
        string original = Subject(service);

        var start = service.StartEmailEntry(new(Email, "Unverified Name"));

        Assert.Equal("email_delivery_unavailable", start.DeliveryMode);
        Assert.Empty(start.TicketId);
        Assert.Equal(original, Subject(Service(mail)));
        Assert.Throws<ArgumentException>(() => service.CompleteEmailEntry(new(start.TicketId)));
    }

    [Fact]
    public void Delivered_links_preserve_existing_profile_before_and_after_restart_and_sign_in()
    {
        var mail = new CapturingMail();
        var service = Service(mail);
        Seed(service);
        string original = Subject(service);
        for (int attempt = 0; attempt < 2; attempt++)
        {
            var start = service.StartEmailEntry(new(" RUNNER@example.invalid ", "Unverified " + attempt, "/account"));
            Assert.Empty(start.TicketId);
            Assert.Equal(SubjectId, start.SubjectId);
            Assert.Equal(original, Subject(service));
            service = Service(mail);
            Assert.Equal(original, Subject(service));
        }

        // The explicit privileged update path remains available. Older pending
        // links must not overwrite even a name changed after those links were sent.
        Seed(service, "Authorized Name");
        string edited = Subject(service);
        foreach (string ticket in mail.Tickets)
        {
            service = Service(mail);
            var session = service.CompleteEmailEntry(new(ticket));
            Assert.Equal(SubjectId, session.SubjectId);
            Assert.Equal(Email, session.Email);
            Assert.Equal("Authorized Name", session.DisplayName);
            Assert.Contains("gm", session.Roles);
            Assert.True(Service(mail).Introspect(new(session.AccessToken)).Active);
            Assert.Equal(edited, Subject(Service(mail)));
            Assert.Throws<KeyNotFoundException>(() => Service(mail).CompleteEmailEntry(new(ticket)));
        }
    }

    [Fact]
    public void New_subject_is_initialized_only_by_a_verified_ticket_and_other_pending_names_cannot_rename_it()
    {
        var mail = new CapturingMail();
        var service = Service(mail);
        string otherSubjectId = IdentitySubjectDerivation.FromEmail("other@example.invalid");
        service.IssueSession(new(otherSubjectId, "Other Runner", "other@example.invalid"));
        string other = JsonSerializer.Serialize(service.GetSubject(otherSubjectId));

        var first = service.StartEmailEntry(new(Email, "Earlier Proposed Name"));
        var second = service.StartEmailEntry(new(Email, "Verified Name"));
        Assert.Empty(first.TicketId);
        Assert.Empty(second.TicketId);
        Assert.Null(service.GetSubject(SubjectId));
        service = Service(mail);
        Assert.Null(service.GetSubject(SubjectId));
        Assert.Throws<KeyNotFoundException>(() => service.CompleteEmailEntry(new("eml_not_a_delivered_ticket")));
        foreach (string ticket in mail.Tickets)
            Assert.DoesNotContain(ticket, File.ReadAllText(StorePath));

        var session = service.CompleteEmailEntry(new(mail.Tickets[1]));
        Assert.Equal(SubjectId, session.SubjectId);
        Assert.Equal(Email, session.Email);
        Assert.Equal("Verified Name", session.DisplayName);
        Assert.Equal(new[] { "player" }, session.Roles);
        string verified = Subject(Service(mail));
        Assert.Equal("Verified Name", Service(mail).CompleteEmailEntry(new(mail.Tickets[0])).DisplayName);
        Assert.Equal(verified, Subject(Service(mail)));
        Assert.Equal(other, JsonSerializer.Serialize(Service(mail).GetSubject(otherSubjectId)));
    }

    [Theory]
    [InlineData("email_delivery_unavailable")]
    [InlineData("email_delivery_failed")]
    public void Failed_new_user_delivery_leaves_no_subject_or_redeemable_ticket(string mode)
    {
        var mail = new CapturingMail(mode);
        var start = Service(mail).StartEmailEntry(new(Email, "Unverified Name"));
        Assert.Empty(start.TicketId);
        var restored = Service(mail);
        Assert.Null(restored.GetSubject(SubjectId));
        Assert.Throws<KeyNotFoundException>(() => restored.CompleteEmailEntry(new(mail.Tickets[0])));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Expiry_or_erasure_of_pending_new_user_cannot_create_a_subject(bool erase)
    {
        var mail = new CapturingMail();
        var service = Service(mail);
        service.StartEmailEntry(new(Email, "Unverified Name"));
        if (erase)
        {
            var result = service.EraseSubject(SubjectId);
            Assert.True(result.Erased);
            Assert.Equal(1, result.DeletedEmailTicketCount);
        }
        else
        {
            var snapshot = JsonNode.Parse(File.ReadAllText(StorePath))!;
            snapshot["emailTickets"]![0]!["expiresAtUtc"] = DateTimeOffset.UtcNow.AddMinutes(-1);
            File.WriteAllText(StorePath, snapshot.ToJsonString());
        }

        service = Service(mail);
        Assert.Throws<KeyNotFoundException>(() => service.CompleteEmailEntry(new(mail.Tickets[0])));
        Assert.Null(service.GetSubject(SubjectId));
    }

    [Fact]
    public void Legacy_stored_ticket_still_signs_in_without_overwriting_the_existing_subject()
    {
        var mail = new CapturingMail();
        var service = Service(mail);
        Seed(service);
        string original = Subject(service);
        service.StartEmailEntry(new(Email, "Legacy Proposed Name"));
        var snapshot = JsonNode.Parse(File.ReadAllText(StorePath))!;
        var ticket = snapshot["emailTickets"]![0]!.AsObject();
        ticket.Remove("ticketHash");
        ticket["ticketId"] = mail.Tickets[0];
        File.WriteAllText(StorePath, snapshot.ToJsonString());

        Assert.Equal("Original Name", Service(mail).CompleteEmailEntry(new(mail.Tickets[0])).DisplayName);
        Assert.Equal(original, Subject(Service(mail)));
        Assert.DoesNotContain(mail.Tickets[0], File.ReadAllText(StorePath));
    }

    private sealed class CapturingMail(string mode = "email_delivered") : IIdentityEmailDeliveryService
    {
        public List<string> Tickets { get; } = [];
        public Action? BeforeDelivery { get; set; }
        public IdentityEmailDeliveryResult DeliverMagicLink(string email, string displayName, string ticketId, string? nextPath, DateTimeOffset expiresAtUtc)
        {
            BeforeDelivery?.Invoke();
            Tickets.Add(ticketId);
            if (mode == "throw") throw new IOException("Synthetic unknown delivery outcome.");
            return new(mode, "Synthetic delivery only", mode == "email_delivered");
        }
        public IdentityEmailDeliveryStatusResponse GetStatus() => new([], [], DateTimeOffset.UtcNow);
        public void RecordStartGuardrailBlock(string email, string deliveryMode, string previewNote) { }
        public IdentityEmailWebhookAckResponse RecordEmailitWebhook(JsonElement payload) => throw new NotSupportedException();
    }

    private sealed class RejectNetwork : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("No network is permitted in this test.");
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
