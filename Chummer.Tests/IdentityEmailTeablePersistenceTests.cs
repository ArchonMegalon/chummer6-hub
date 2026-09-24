using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class IdentityEmailTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "identity-mail-primary-" + Guid.NewGuid().ToString("N"));
    private readonly DateTimeOffset _expiry = DateTimeOffset.UtcNow.AddMinutes(15);
    private IConfiguration Configuration(string host = "first", string order = "emailit_api") => new ConfigurationBuilder()
        .AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_IDENTITY_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_IDENTITY_STORE_PATH"] = Path.Combine(_root, host, "identity.json"),
            ["CHUMMER_IDENTITY_EMAIL_DELIVERY_STORE_PATH"] = Path.Combine(_root, host, "email.json"),
            ["IDENTITY_EMAIL_PROVIDER_ORDER"] = order,
            ["IDENTITY_EMAILIT_API_KEY"] = "synthetic-provider-secret",
            ["IDENTITY_EMAILIT_FROM_EMAIL"] = "sender@example.invalid",
            ["IDENTITY_EMAIL_START_ENABLED"] = "true",
            ["IDENTITY_PUBLIC_BASE_URL"] = "https://chummer.example",
            ["IDENTITY_EMAIL_START_MIN_SECONDS_BETWEEN_RECIPIENT_ATTEMPTS"] = "120"
        }).Build();
    private IdentityEmailDeliveryService Service(Remote remote, Provider provider, string host = "first") =>
        new(Configuration(host), NullLogger<IdentityEmailDeliveryService>.Instance, new HttpClient(provider, false), remote.Store());
    private IdentityEmailDeliveryResult Send(IdentityEmailDeliveryService service, string ticket = "synthetic-ticket",
        string email = "runner@example.invalid") => service.DeliverMagicLink(email, "Synthetic", ticket, "/home", _expiry);

    [Fact]
    public void Accepted_dispatch_and_webhook_recipient_restore_without_files_or_plaintext_tickets()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var first = Service(remote, provider);
        var accepted = Send(first);
        Assert.True(accepted.Delivered);
        var cold = Service(remote, provider, "new-host");
        Assert.Equal(accepted, Send(cold));
        Assert.Equal(1, provider.Sends);
        using var webhook = JsonDocument.Parse("""{"type":"email.delivered","data":{"id":"email_synthetic"}}""");
        cold.RecordEmailitWebhook(webhook.RootElement);
        var status = first.GetStatus(); // Existing instance must also read current history.
        Assert.Contains(status.RecentDeliveries, row => row.EmailKind == "webhook" && row.RecipientEmail == "runner@example.invalid");
        Assert.Equal("delivered", Assert.Single(status.Recipients).State);
        Assert.False(Directory.Exists(_root));
        foreach (var row in remote.Rows.Values.Where(row => row["kind"]!.GetValue<string>() == "chunk"))
        {
            string payload = Encoding.UTF8.GetString(Convert.FromBase64String(row["payload"]!.GetValue<string>()));
            Assert.DoesNotContain("synthetic-ticket", payload);
            Assert.DoesNotContain("synthetic-provider-secret", payload);
            Assert.DoesNotContain("auth/email/callback", payload);
        }
    }

    [Fact]
    public void Trimming_recent_events_does_not_drop_dispatch_fences_or_rebind_a_ticket()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var service = Service(remote, provider);
        var accepted = Send(service);
        for (int index = 0; index < 101; index++)
            service.RecordStartGuardrailBlock("runner@example.invalid", "disabled", "Synthetic guardrail");
        var cold = Service(remote, provider, "new-host");
        Assert.Equal(40, cold.GetStatus().RecentDeliveries.Count);
        Assert.Equal(accepted, Send(cold));
        Assert.Throws<InvalidOperationException>(() => Send(cold, email: "foreign@example.invalid"));
        Assert.Equal(1, provider.Sends);
    }

    [Fact]
    public void Competing_admission_sends_once_and_loser_never_falls_back()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var first = Service(remote, provider);
        var other = Service(remote, provider, "other");
        remote.BeforeHeadPost = () => Assert.True(Send(other).Delivered);
        Assert.Throws<Chummer.Storage.Teable.TeableRevisionConflictException>(() => Send(first));
        Assert.Throws<InvalidOperationException>(() => first.GetStatus());
        Assert.True(Send(Service(remote, provider, "cold")).Delivered);
        Assert.Equal(1, provider.Sends);
    }

    [Fact]
    public void Uncertain_admission_never_dispatches_even_after_cold_recovery()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var service = Service(remote, provider);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => Send(service));
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => Send(service));
        var restored = Send(Service(remote, provider, "cold"));
        Assert.False(restored.Delivered);
        Assert.Equal("email_delivery_unknown", restored.DeliveryMode);
        Assert.Equal(0, provider.Sends);
        Assert.Equal(posts, remote.HeadPosts);
    }

    [Fact]
    public void Uncertain_finalization_is_read_back_without_resending()
    {
        using var remote = new Remote();
        using var provider = new Provider { OnSend = () => remote.CommitThenFailHard = true };
        var service = Service(remote, provider);
        Assert.Throws<IOException>(() => Send(service));
        int posts = remote.HeadPosts;
        Assert.True(Send(Service(remote, provider, "cold")).Delivered);
        Assert.Equal(1, provider.Sends);
        Assert.Equal(posts, remote.HeadPosts);
    }

    [Fact]
    public void Finalization_conflict_leaves_pending_fence_and_preserves_other_history()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var other = Service(remote, provider, "other");
        provider.OnSend = () => remote.BeforeHeadPost = () =>
            other.RecordStartGuardrailBlock("other@example.invalid", "disabled", "Synthetic guardrail");
        Assert.Throws<Chummer.Storage.Teable.TeableRevisionConflictException>(() => Send(Service(remote, provider)));
        var cold = Service(remote, provider, "cold");
        Assert.Equal("email_delivery_unknown", Send(cold).DeliveryMode);
        Assert.Contains(cold.GetStatus().RecentDeliveries, item => item.RecipientEmail == "other@example.invalid");
        Assert.Equal(1, provider.Sends);
    }

    [Fact]
    public void Webhook_during_send_is_not_overwritten_by_later_acceptance()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var other = Service(remote, provider, "webhook-host");
        provider.OnSend = () =>
        {
            using var payload = JsonDocument.Parse("""{"type":"email.bounced","data":{"id":"email_synthetic","to":"runner@example.invalid"}}""");
            other.RecordEmailitWebhook(payload.RootElement);
        };
        Assert.True(Send(Service(remote, provider)).Delivered); // Provider acceptance, not inbox delivery.
        var cold = Service(remote, provider, "cold");
        Assert.Equal("bounced", Assert.Single(cold.GetStatus().Recipients).State);
        Assert.Contains(cold.GetStatus().RecentDeliveries, row => row.EmailKind == "webhook");
        Assert.True(Send(cold).Delivered);
        Assert.Equal(1, provider.Sends);
    }

    [Fact]
    public void Lost_storage_read_after_provider_acceptance_keeps_pending_fence_on_cold_restore()
    {
        using var remote = new Remote();
        using var provider = new Provider { OnSend = () => remote.FailReads = true };
        Assert.Throws<HttpRequestException>(() => Send(Service(remote, provider)));
        remote.FailReads = false;
        Assert.Equal("email_delivery_unknown", Send(Service(remote, provider, "cold")).DeliveryMode);
        Assert.Equal(1, provider.Sends);
    }

    [Fact]
    public void Disabled_provider_does_not_expose_an_inline_preview_in_primary_mode()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var config = Configuration(order: "none");
        config["IDENTITY_UNSAFE_ALLOW_INLINE_EMAIL_PREVIEW_LINKS"] = "true";
        config["ASPNETCORE_ENVIRONMENT"] = "Development";
        config["IDENTITY_PUBLIC_BASE_URL"] = "http://localhost:5101";
        var mail = new IdentityEmailDeliveryService(config, NullLogger<IdentityEmailDeliveryService>.Instance,
            new HttpClient(provider, false), remote.Store());
        var result = Send(mail);
        Assert.Equal("email_delivery_unavailable", result.DeliveryMode);
        Assert.False(result.ExposeInlinePreviewTicket);
        Assert.Contains(Service(remote, provider, "cold").GetStatus().RecentDeliveries, item => item.Status == "unavailable");
        Assert.Equal(0, provider.Sends);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Provider_failure_is_durable_unknown_and_does_not_expose_provider_body_or_exception(bool throws)
    {
        using var remote = new Remote();
        using var provider = new Provider { Fail = !throws, Throw = throws };
        var result = Send(Service(remote, provider));
        Assert.Equal("email_delivery_unknown", result.DeliveryMode);
        var cold = Service(remote, provider, "cold");
        Assert.Equal(result, Send(cold));
        Assert.DoesNotContain("sensitive-provider-diagnostic", JsonSerializer.Serialize(cold.GetStatus()));
        Assert.Equal(1, provider.Sends);
    }

    [Fact]
    public void Primary_outage_rejects_cached_status_and_dispatch_without_using_local_snapshot()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var service = Service(remote, provider);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => service.GetStatus());
        Assert.Throws<HttpRequestException>(() => Send(service));
        Assert.Throws<HttpRequestException>(() => Service(remote, provider, "cold"));
        Assert.Equal(0, provider.Sends);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public async Task Malformed_primary_history_is_rejected_not_replaced()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        await remote.Store().CompareExchangeAsync("identity-email-delivery", null, Guid.NewGuid(), "{}"u8.ToArray());
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => Service(remote, provider));
        Assert.Equal(posts, remote.HeadPosts);
        Assert.Equal(0, provider.Sends);
    }

    [Fact]
    public void Explicit_primary_registration_is_required_and_local_history_is_not_imported()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        Assert.Throws<InvalidOperationException>(() => new IdentityEmailDeliveryService(Configuration(),
            NullLogger<IdentityEmailDeliveryService>.Instance));
        string path = Path.Combine(_root, "first", "email.json");
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, "retained-local-state");
        Assert.Empty(Service(remote, provider).GetStatus().RecentDeliveries);
        Assert.Equal("retained-local-state", File.ReadAllText(path));
    }

    [Fact]
    public void Identity_dependency_injection_selects_primary_mail_without_a_provider_call()
    {
        using var remote = new Remote();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(Configuration(order: "none"));
        services.AddLogging();
        services.AddSingleton(remote.Store());
        services.AddSingleton<IIdentityEmailDeliveryService, IdentityEmailDeliveryService>();
        services.AddSingleton<IdentityAccessService>();
        using var container = services.BuildServiceProvider(new ServiceProviderOptions { ValidateOnBuild = true });
        Assert.True(container.GetRequiredService<IdentityAccessService>().IsStorageReady());
        Assert.Empty(container.GetRequiredService<IIdentityEmailDeliveryService>().GetStatus().RecentDeliveries);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Real_identity_service_and_mail_history_restore_together_after_discarding_the_host()
    {
        using var remote = new Remote();
        using var provider = new Provider();
        var mail = Service(remote, provider);
        var identity = new IdentityAccessService(Configuration(), NullLogger<IdentityAccessService>.Instance, mail, remote.Store());
        var entry = identity.StartEmailEntry(new("runner@example.invalid", "Synthetic"));
        Assert.Equal("emailit_api_magic_link", entry.DeliveryMode);
        Assert.Equal(string.Empty, entry.TicketId);
        Assert.NotNull(provider.Body);
        using var body = JsonDocument.Parse(provider.Body!);
        string ticket = Regex.Match(body.RootElement.GetProperty("text").GetString()!, @"ticket=([^&\s]+)").Groups[1].Value;
        Assert.StartsWith("eml_", ticket);
        var coldMail = Service(remote, provider, "cold");
        var cold = new IdentityAccessService(Configuration("cold"), NullLogger<IdentityAccessService>.Instance, coldMail, remote.Store());
        var session = cold.CompleteEmailEntry(new(ticket));
        Assert.True(cold.Introspect(new(session.AccessToken)).Active);
        Assert.Throws<KeyNotFoundException>(() => cold.CompleteEmailEntry(new(ticket)));
        Assert.Contains(coldMail.GetStatus().RecentDeliveries, item => item.Delivered);
        cold.StartEmailEntry(new("runner@example.invalid", "Synthetic")); // Restored cooldown must not redispatch.
        Assert.Equal(1, provider.Sends);
        Assert.False(Directory.Exists(_root));
    }

    private sealed class Provider : HttpMessageHandler
    {
        public int Sends;
        public bool Fail;
        public bool Throw;
        public string? Body;
        public Action? OnSend;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Sends++;
            Body = await request.Content!.ReadAsStringAsync(cancellationToken);
            OnSend?.Invoke();
            if (Throw) throw new HttpRequestException("sensitive-provider-diagnostic");
            return new HttpResponseMessage(Fail ? HttpStatusCode.ServiceUnavailable : HttpStatusCode.Accepted)
            {
                Content = new StringContent(Fail ? "sensitive-provider-diagnostic" : """{"data":{"id":"email_synthetic"}}""", Encoding.UTF8, "application/json")
            };
        }
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, true); }
}
