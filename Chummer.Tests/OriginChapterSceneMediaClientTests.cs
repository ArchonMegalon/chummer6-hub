using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginChapterSceneMediaClientTests
{
    [Fact]
    public async Task Private_socket_binds_owner_and_rechecks_authorization_after_io()
    {
        if (!OperatingSystem.IsLinux()) return;
        bool current = true;
        using var peer = new Peer(request =>
        {
            Assert.StartsWith("POST /v1/read HTTP/1.1", request);
            Assert.Contains("Authorization: Bearer " + Peer.TestToken, request);
            Assert.Contains(Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes("subject-a"))), request);
            Assert.DoesNotContain("subject-a", request);
            current = false;
            return "{\"state\":\"review\"}";
        });
        await Assert.ThrowsAsync<UnauthorizedAccessException>(() => peer.Client.ReadAsync("subject-a", new string('a', 64), () => current, default));
        await peer.Completed;
    }

    [Fact]
    public async Task Private_socket_read_uses_no_provider_or_public_url()
    {
        if (!OperatingSystem.IsLinux()) return;
        using var peer = new Peer(_ => "{\"state\":\"persisted\",\"publicationAuthorized\":false}");
        JsonElement result = await peer.Client.ReadAsync("subject-a", new string('a', 64), () => true, default);
        Assert.Equal("persisted", result.GetProperty("state").GetString());
        Assert.False(result.GetProperty("publicationAuthorized").GetBoolean());
        await peer.Completed;
    }

    [Theory]
    [InlineData("302 Found", "Location: https://provider.invalid/private\r\n")]
    [InlineData("200 OK", "Content-Length: 99999999\r\n")]
    public async Task Redirects_and_oversized_headers_fail_without_reading_private_body(string status, string headers)
    {
        if (!OperatingSystem.IsLinux()) return;
        using var peer = new Peer(_ => "{}", status, headers);
        await Assert.ThrowsAsync<InvalidDataException>(() => peer.Client.ReadAsync("subject-a", new string('a', 64), () => true, default));
        await peer.Completed;
    }

    [Fact]
    public async Task Account_erasure_checks_supported_worker_and_validates_exact_owner()
    {
        if (!OperatingSystem.IsLinux()) return;
        using (var peer = new Peer(_ => "{\"schema\":\"chummer.media.origin-scene-worker/v1\",\"accountErasureSupported\":true}"))
        {
            peer.Client.EnsureAccountErasureSupported();
            await peer.Completed;
        }
        using (var peer = new Peer(_ => "{\"ownerDigest\":\"wrong\",\"recordsRemoved\":1}"))
        {
            Assert.Throws<InvalidDataException>(() => peer.Client.EraseForSubject("subject-a"));
            await peer.Completed;
        }
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public async Task Recovery_only_worker_is_readable_but_cannot_admit_new_dispatch(bool dispatchEnabled)
    {
        if (!OperatingSystem.IsLinux()) return;
        using var peer = new Peer(_ => JsonSerializer.Serialize(new
        {
            schema = "chummer.media.origin-scene-worker/v1", accountErasureSupported = true, dispatchEnabled
        }));
        if (dispatchEnabled) await peer.Client.EnsureDispatchAvailableAsync(default);
        else await Assert.ThrowsAsync<InvalidOperationException>(() => peer.Client.EnsureDispatchAvailableAsync(default));
        await peer.Completed;
    }

    [Fact]
    public void Never_enabled_media_is_optional_but_required_or_partial_configuration_fails_closed()
    {
        var empty = new ConfigurationBuilder().Build();
        new OriginSceneMediaClient(empty).EnsureAccountErasureSupported();
        foreach (string key in new[] { "CHUMMER_ORIGIN_SCENE_MEDIA_REQUIRED", "CHUMMER_ORIGIN_SCENE_MEDIA_SOCKET" })
        {
            var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { [key] = "true" }).Build();
            Assert.Throws<InvalidOperationException>(() => new OriginSceneMediaClient(config).EnsureAccountErasureSupported());
        }
    }

    [Fact]
    public async Task Compose_only_receipt_cannot_reach_worker_or_spend_credits()
    {
        var request = new HorizonArtifactRequestCreateRequest("origin-dossier", "origin-dossier-media", "user-a",
            "origin-dossier:scene:" + new string('a', 64), "private", true);
        var receipt = new HorizonArtifactRequestService(new(new ConfigurationBuilder().Build()))
            .BuildRequest(request, requireEnabledCapability: false);
        Assert.Equal("accepted", receipt.Status);
        await Assert.ThrowsAsync<InvalidOperationException>(() => new OriginSceneMediaClient(new ConfigurationBuilder().Build())
            .RenderAsync("subject-a", receipt, () => true, default));
    }

    private sealed class Peer : IDisposable
    {
        internal const string TestToken = "synthetic-origin-worker-test-token-only";
        private readonly string directory = Path.Combine(Path.GetTempPath(), "scene-peer-" + Guid.NewGuid().ToString("N"));
        private readonly Socket listener;
        private readonly CancellationTokenSource deadline = new(TimeSpan.FromSeconds(10));
        public OriginSceneMediaClient Client { get; }
        public Task Completed { get; }

        public Peer(Func<string, string> reply, string status = "200 OK", string extraHeaders = "")
        {
            if (!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException();
            Directory.CreateDirectory(directory, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            string path = Path.Combine(directory, "worker.sock");
            string token = Path.Combine(directory, "token");
            File.WriteAllText(token, TestToken);
            File.SetUnixFileMode(token, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            listener = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
            listener.Bind(new UnixDomainSocketEndPoint(path));
            listener.Listen(1);
            Client = new(new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_ORIGIN_SCENE_MEDIA_SOCKET"] = path,
                ["CHUMMER_ORIGIN_SCENE_MEDIA_TOKEN_FILE"] = token
            }).Build());
            Completed = Task.Run(async () =>
            {
                using Socket connection = await listener.AcceptAsync(deadline.Token);
                using var stream = new NetworkStream(connection, ownsSocket: false);
                using var reader = new StreamReader(stream, Encoding.UTF8, leaveOpen: true);
                var packet = new StringBuilder();
                int length = 0;
                string? line;
                while (!string.IsNullOrEmpty(line = await reader.ReadLineAsync(deadline.Token)))
                {
                    packet.AppendLine(line);
                    if (line.StartsWith("Content-Length: ", StringComparison.OrdinalIgnoreCase)) length = int.Parse(line[16..]);
                    if (packet.Length > 8192) throw new InvalidDataException();
                }
                if (length is < 0 or > 65536) throw new InvalidDataException();
                char[] body = new char[length];
                int read = 0;
                while (read < length)
                {
                    int count = await reader.ReadAsync(body.AsMemory(read), deadline.Token);
                    if (count == 0) throw new EndOfStreamException();
                    read += count;
                }
                packet.Append(body);
                byte[] output = Encoding.UTF8.GetBytes(reply(packet.ToString()));
                string framing = extraHeaders.Contains("Content-Length:", StringComparison.Ordinal)
                    ? extraHeaders : extraHeaders + $"Content-Length: {output.Length}\r\n";
                byte[] head = Encoding.ASCII.GetBytes($"HTTP/1.1 {status}\r\nContent-Type: application/json\r\n{framing}Connection: close\r\n\r\n");
                await stream.WriteAsync(head, deadline.Token);
                await stream.WriteAsync(output, deadline.Token);
            });
        }

        public void Dispose()
        {
            deadline.Cancel();
            listener.Dispose();
            try { Completed.GetAwaiter().GetResult(); } catch (OperationCanceledException) { }
            deadline.Dispose();
            Directory.Delete(directory, true);
        }
    }
}
