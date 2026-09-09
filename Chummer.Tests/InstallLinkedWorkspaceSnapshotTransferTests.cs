using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text;
using System.Text.Encodings.Web;
using System.Reflection;
using Chummer.Contracts.Characters;
using Chummer.Contracts.Workspaces;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkedWorkspaceSnapshotTransferTests
{
    [Fact]
    public void Empty_snapshot_digest_matches_independent_canonical_wire_vector()
    {
        var snapshot = new WorkspaceDocumentSnapshot(new("ws-golden"), new WorkspaceDocument(
            new WorkspaceDocumentState("sr5", 1, "workspace", "payload")),
            new DateTimeOffset(2026, 9, 9, 12, 0, 0, TimeSpan.Zero), 1, 0);
        // Independently hashed wire vector: the generic UTF-8 JSON writer
        // escapes the timestamp's plus sign as \u002B, unlike JSON.stringify.
        Assert.Equal("afe09168141e45cb41d520b9faa993b6895a46e2e27a70c4829cfdd530c2c315",
            InstallLinkedWorkspaceSnapshotTransfer.ComputeDigest(InstallLinkedWorkspaceSnapshotTransfer.Encode(snapshot)));
    }

    [Theory]
    [InlineData("MixedSubject", "mixedSubject", "ws-transfer", "ws-transfer")]
    [InlineData("subject", "subject|part", "part|ws-transfer", "ws-transfer")]
    public void Opaque_owner_and_workspace_components_never_alias(string firstOwner, string secondOwner, string firstId, string secondId)
    {
        using Fixture fixture = new();
        var a = fixture.Installation with { SubjectId = firstOwner };
        var b = fixture.Installation with { SubjectId = secondOwner };
        var core = SampleSnapshot();
        fixture.Service.UpsertForInstallation(a, ToRecord(core with { Id = new(firstId) }), 0);
        Assert.Empty(fixture.Service.ListForInstallation(b));
        var second = fixture.Service.UpsertForInstallation(b, ToRecord(core with { Id = new(secondId) }), 0);
        Assert.Equal(1, second.RemoteRevision);
        var reloaded = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
        Assert.Equal(firstId, Assert.Single(reloaded.ListForInstallation(a)).WorkspaceId);
        Assert.Equal(secondId, Assert.Single(reloaded.ListForInstallation(b)).WorkspaceId);
    }

    public static IEnumerable<object[]> AuxiliaryMembers()
        => typeof(WorkspaceDocumentAuxiliaryState).GetProperties()
            .Where(static p => p.SetMethod is not null).Select(static p => new object[] { p.Name });

    [Theory]
    [MemberData(nameof(AuxiliaryMembers))]
    public void Every_current_core_auxiliary_member_roundtrips_without_being_discarded(string member)
    {
        using Fixture fixture = new();
        var property = typeof(WorkspaceDocumentAuxiliaryState).GetProperty(member)!;
        var auxiliary = new WorkspaceDocumentAuxiliaryState();
        property.SetValue(auxiliary, TransportFixture(property.PropertyType, []));
        var core = SampleSnapshot();
        core = core with { Document = core.Document with { State = core.Document.State with { AuxiliaryState = auxiliary } } };
        var record = fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(core), 0);
        var reloaded = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
        var restored = InstallLinkedWorkspaceSnapshotTransfer.Decode(
            Assert.Single(reloaded.ListForInstallation(fixture.Installation)).WorkspaceSnapshot!.Value);
        Assert.NotNull(property.GetValue(restored.Document.AuxiliaryState));
        Assert.Equal(core.Document.AuxiliaryStateDigest, restored.Document.AuxiliaryStateDigest);
        Assert.Equal(record.WorkspaceSnapshotDigest, ToRecord(restored).WorkspaceSnapshotDigest);
    }

    // Populate actual Core contracts (including nonempty receipt arrays), not
    // mirrored DTOs. Values exercise serialization, not mechanical legality.
    private static object? TransportFixture(Type type, HashSet<Type> ancestors)
    {
        Type? nullable = Nullable.GetUnderlyingType(type);
        if (nullable is not null) return TransportFixture(nullable, ancestors);
        if (type == typeof(string)) return "fixture";
        if (type == typeof(bool)) return true;
        if (type == typeof(Guid)) return Guid.Parse("184943db-280a-4853-b8f9-4e09b78a694e");
        if (type == typeof(DateTimeOffset)) return new DateTimeOffset(2026, 9, 9, 12, 0, 0, TimeSpan.Zero);
        if (type == typeof(DateTime)) return new DateTime(2026, 9, 9, 12, 0, 0, DateTimeKind.Utc);
        if (type.IsEnum) return Enum.GetValues(type).GetValue(0);
        if (type.IsPrimitive || type == typeof(decimal)) return Convert.ChangeType(1, type, System.Globalization.CultureInfo.InvariantCulture);
        if (type == typeof(WorkspaceDocumentAuxiliaryState)) return new WorkspaceDocumentAuxiliaryState();
        if (type.IsGenericType && type.GetGenericTypeDefinition() is var dictionary
            && (dictionary == typeof(IReadOnlyDictionary<,>) || dictionary == typeof(Dictionary<,>)))
        {
            Type[] arguments = type.GetGenericArguments();
            var instance = (System.Collections.IDictionary)Activator.CreateInstance(typeof(Dictionary<,>).MakeGenericType(arguments))!;
            instance.Add(TransportFixture(arguments[0], ancestors)!, TransportFixture(arguments[1], ancestors));
            return instance;
        }
        if (type.IsArray || (type.IsGenericType && type.GetGenericTypeDefinition() is var collection
            && (collection == typeof(IReadOnlyList<>) || collection == typeof(IReadOnlyCollection<>) || collection == typeof(IEnumerable<>))))
        {
            Type element = type.IsArray ? type.GetElementType()! : type.GetGenericArguments()[0];
            Array result = Array.CreateInstance(element, 1);
            result.SetValue(TransportFixture(element, ancestors), 0);
            return result;
        }
        Assert.DoesNotContain(type, ancestors);
        HashSet<Type> next = new(ancestors) { type };
        ConstructorInfo constructor = type.GetConstructors().OrderByDescending(static c => c.GetParameters().Length).First();
        return constructor.Invoke(constructor.GetParameters().Select(p => TransportFixture(p.ParameterType, next)).ToArray());
    }

    [Fact]
    public void Failed_full_snapshot_write_preserves_prior_receipts_and_allows_exact_retry()
    {
        using Fixture fixture = new();
        var core = SampleSnapshot();
        var before = fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(core), 0);
        var changed = ToRecord(core with { ContentRevision = 8, SavedRevision = 8 });
        string fault = fixture.Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]! + ".tmp";
        Directory.CreateDirectory(fault);
        try
        {
            Exception? failure = Record.Exception(() => fixture.Service.UpsertForInstallation(
                fixture.Installation, changed, before.RemoteRevision, before.ServerToken));
            Assert.True(failure is IOException or UnauthorizedAccessException);
            var current = Assert.Single(fixture.Service.ListForInstallation(fixture.Installation));
            Assert.Equal(before.WorkspaceSnapshotDigest, current.WorkspaceSnapshotDigest);
            Assert.Equal(before.ServerToken, current.ServerToken);
            var disk = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
            Assert.Equal(before.WorkspaceSnapshotDigest, Assert.Single(disk.ListForInstallation(fixture.Installation)).WorkspaceSnapshotDigest);
        }
        finally { Directory.Delete(fault); }
        var retry = fixture.Service.UpsertForInstallation(fixture.Installation, changed, before.RemoteRevision, before.ServerToken);
        Assert.Equal(2, retry.RemoteRevision);
        Assert.Equal(8, InstallLinkedWorkspaceSnapshotTransfer.Decode(retry.WorkspaceSnapshot!.Value).SavedRevision);
    }

    [Fact]
    public void Full_core_snapshot_survives_commit_cold_read_and_idempotent_retry()
    {
        using Fixture fixture = new();
        WorkspaceDocumentSnapshot core = SampleSnapshot();
        InstallLinkedWorkspaceSnapshotRecord request = ToRecord(core);
        var first = fixture.Service.UpsertForInstallation(fixture.Installation, request, 0);
        var reloaded = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
        var second = Assert.Single(reloaded.ListForInstallation(fixture.Installation));
        WorkspaceDocumentSnapshot restored = InstallLinkedWorkspaceSnapshotTransfer.Decode(second.WorkspaceSnapshot!.Value);
        Assert.Equal(core.Id, restored.Id);
        Assert.Equal(core.ContentRevision, restored.ContentRevision);
        Assert.Equal(core.SavedRevision, restored.SavedRevision);
        Assert.Equal(core.Document.AuxiliaryStateDigest, restored.Document.AuxiliaryStateDigest);
        Assert.Equal("Straßenkind — live choice", restored.Document.AuxiliaryState.CharacterCreationFoundationDraft!.FollowUpValues["story"]);
        Assert.NotNull(restored.Document.AuxiliaryState.CharacterCreationFinalizationArchive);
        Assert.NotNull(restored.Document.AuxiliaryState.CharacterCreationSkillsReceipts);
        Assert.Equal(first.WorkspaceSnapshotDigest, second.WorkspaceSnapshotDigest);
        var retried = reloaded.UpsertForInstallation(fixture.Installation, request, second.RemoteRevision, second.ServerToken);
        Assert.Equal(second.RemoteRevision, retried.RemoteRevision);
        Assert.Equal(second.ServerToken, retried.ServerToken);
        Assert.Empty(reloaded.ListForInstallation(fixture.Installation with { SubjectId = "other-owner" }));
    }

    [Fact]
    public void Near_limit_compact_snapshot_survives_indented_store_cold_reload()
    {
        using Fixture fixture = new();
        var empty = ToRecord(SnapshotWithFoundationTransportText(string.Empty));
        int overhead = Encoding.UTF8.GetByteCount(empty.WorkspaceSnapshot!.Value.GetRawText());
        string story = new('x', InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes - 64 - overhead);
        var core = SnapshotWithFoundationTransportText(story);
        var request = ToRecord(core);
        int compactBytes = Encoding.UTF8.GetByteCount(request.WorkspaceSnapshot!.Value.GetRawText());
        Assert.Equal(InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes - 64, compactBytes);
        Assert.True(compactBytes + Encoding.UTF8.GetByteCount(request.Payload)
            < InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes);

        var committed = fixture.Service.UpsertForInstallation(fixture.Installation, request, 0);
        Assert.Equal(committed.WorkspaceSnapshotDigest,
            Assert.Single(fixture.Service.ListForInstallation(fixture.Installation)).WorkspaceSnapshotDigest);
        string path = fixture.Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!;
        using (JsonDocument persisted = JsonDocument.Parse(File.ReadAllText(path)))
        {
            JsonElement stored = persisted.RootElement.GetProperty("snapshots")[0].GetProperty("workspaceSnapshot");
            Assert.True(Encoding.UTF8.GetByteCount(stored.GetRawText())
                > InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes,
                "The fixture must cross the raw snapshot bound through persisted indentation alone.");
        }

        var reloaded = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
        var read = Assert.Single(reloaded.ListForInstallation(fixture.Installation));
        var restored = InstallLinkedWorkspaceSnapshotTransfer.Decode(read.WorkspaceSnapshot!.Value);
        Assert.Equal(story, restored.Document.AuxiliaryState.CharacterCreationFoundationDraft!.FollowUpValues["story"]);
        Assert.Equal(core.Document.AuxiliaryStateDigest, restored.Document.AuxiliaryStateDigest);
        Assert.Equal(committed.RemoteRevision, read.RemoteRevision);
        Assert.Equal(committed.ServerToken, read.ServerToken);
        Assert.Equal(committed.WorkspaceSnapshotDigest, read.WorkspaceSnapshotDigest);
    }

    [Fact]
    public void Oversized_incoming_whitespace_is_rejected_even_when_canonical_snapshot_is_small()
    {
        using Fixture fixture = new();
        var request = ToRecord(SampleSnapshot());
        var before = fixture.Service.UpsertForInstallation(fixture.Installation, request, 0);
        string path = fixture.Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!;
        byte[] originalBytes = File.ReadAllBytes(path);
        string compact = request.WorkspaceSnapshot!.Value.GetRawText();
        using JsonDocument padded = JsonDocument.Parse("{" +
            new string(' ', InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes) + compact[1..]);
        int rawBytes = Encoding.UTF8.GetByteCount(padded.RootElement.GetRawText());
        Assert.True(rawBytes > InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes);
        Assert.True(rawBytes + Encoding.UTF8.GetByteCount(request.Payload)
            < InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes);
        request = request with { WorkspaceSnapshot = padded.RootElement.Clone() };

        Assert.Equal(StatusCodes.Status400BadRequest, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.UpsertForInstallation(fixture.Installation, request,
                before.RemoteRevision, before.ServerToken)).StatusCode);
        Assert.Equal(originalBytes, File.ReadAllBytes(path));
        Assert.Equal(before.ServerToken,
            Assert.Single(fixture.Service.ListForInstallation(fixture.Installation)).ServerToken);
    }

    [Fact]
    public void Compact_unicode_input_exceeding_canonical_snapshot_bound_is_rejected_before_write()
    {
        using Fixture fixture = new();
        var before = fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(SampleSnapshot()), 0);
        string path = fixture.Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!;
        byte[] persistedBefore = File.ReadAllBytes(path);
        var request = ToRecord(SnapshotWithFoundationTransportText(
            new string('ä', InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes / 3)));
        Assert.True(Encoding.UTF8.GetByteCount(request.WorkspaceSnapshot!.Value.GetRawText())
            > InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes);
        // The caller sends literal UTF-8; Core's transport encoder emits six-byte
        // Unicode escapes. Both JSON forms represent the same transport fixture.
        string compact = JsonSerializer.Serialize(request.WorkspaceSnapshot!.Value,
            new JsonSerializerOptions { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping });
        using JsonDocument incoming = JsonDocument.Parse(compact);
        int incomingBytes = Encoding.UTF8.GetByteCount(incoming.RootElement.GetRawText());
        Assert.True(incomingBytes < InstallLinkedWorkspaceSnapshotTransfer.MaxSnapshotBytes);
        Assert.True(incomingBytes + Encoding.UTF8.GetByteCount(request.Payload)
            < InstallLinkedWorkspaceSnapshotService.MaxUpsertRequestBodyBytes);
        request = request with { WorkspaceSnapshot = incoming.RootElement.Clone() };

        Assert.Equal(StatusCodes.Status400BadRequest, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.UpsertForInstallation(fixture.Installation, request,
                before.RemoteRevision, before.ServerToken)).StatusCode);
        Assert.Equal(persistedBefore, File.ReadAllBytes(path));
        var unchanged = Assert.Single(fixture.Service.ListForInstallation(fixture.Installation));
        Assert.Equal(before.RemoteRevision, unchanged.RemoteRevision);
        Assert.Equal(before.ServerToken, unchanged.ServerToken);
        Assert.Equal(before.WorkspaceSnapshotDigest, unchanged.WorkspaceSnapshotDigest);
    }

    [Fact]
    public void Caller_json_lifetime_does_not_own_stored_snapshot_bytes()
    {
        using Fixture fixture = new();
        var request = ToRecord(SampleSnapshot());
        using (JsonDocument input = JsonDocument.Parse(request.WorkspaceSnapshot!.Value.GetRawText()))
            fixture.Service.UpsertForInstallation(fixture.Installation, request with { WorkspaceSnapshot = input.RootElement }, 0);
        var restored = Assert.Single(fixture.Service.ListForInstallation(fixture.Installation));
        Assert.Equal(request.WorkspaceSnapshotDigest, restored.WorkspaceSnapshotDigest);
        Assert.Equal(SampleSnapshot().Document.AuxiliaryStateDigest,
            InstallLinkedWorkspaceSnapshotTransfer.Decode(restored.WorkspaceSnapshot!.Value).Document.AuxiliaryStateDigest);
    }

    [Theory]
    [InlineData("id")]
    [InlineData("ruleset")]
    [InlineData("format")]
    [InlineData("schema")]
    [InlineData("kind")]
    [InlineData("payload")]
    [InlineData("updated")]
    [InlineData("revision-zero")]
    [InlineData("revision-negative")]
    [InlineData("saved-future")]
    [InlineData("saved-negative")]
    [InlineData("digest")]
    [InlineData("missing-digest")]
    [InlineData("missing-snapshot")]
    [InlineData("unknown-property")]
    [InlineData("unknown-auxiliary")]
    [InlineData("unknown-receipt-field")]
    [InlineData("computed-property")]
    [InlineData("duplicate-property")]
    [InlineData("null-auxiliary")]
    [InlineData("oversized")]
    public void Inconsistent_or_lossy_transport_never_changes_remote_authority(string corruption)
    {
        using Fixture fixture = new();
        var initial = fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(SampleSnapshot()), 0);
        var request = ToRecord(SampleSnapshot());
        JsonObject json = JsonNode.Parse(request.WorkspaceSnapshot!.Value.GetRawText())!.AsObject();
        JsonObject state = json["document"]!["state"]!.AsObject();
        switch (corruption)
        {
            case "id": json["id"]!["value"] = "other-workspace"; break;
            case "ruleset": state["rulesetId"] = "sr6"; break;
            case "format": json["document"]!["format"] = 93; break;
            case "schema": state["schemaVersion"] = 3; break;
            case "kind": state["payloadKind"] = "other"; break;
            case "payload": state["payload"] = "different"; break;
            case "updated": json["lastUpdatedUtc"] = "2026-09-08T12:00:00Z"; break;
            case "revision-zero": json["contentRevision"] = 0; break;
            case "revision-negative": json["contentRevision"] = -1; break;
            case "saved-future": json["savedRevision"] = 900; break;
            case "saved-negative": json["savedRevision"] = -1; break;
            case "unknown-property": json["forgottenScope"] = "must not discard"; break;
            case "unknown-auxiliary": state["auxiliaryState"]!["futureWizard"] = new JsonObject(); break;
            case "unknown-receipt-field": state["auxiliaryState"]!["characterCreationFoundationDraft"]!["privateCargo"] = "no"; break;
            case "computed-property": state["auxiliaryState"]!["isEmpty"] = true; break;
            case "null-auxiliary": state["auxiliaryState"] = null; break;
            case "oversized": state["auxiliaryState"]!["characterCreationFoundationDraft"]!["followUpValues"]!["story"] = new string('ä', 300_000); break;
        }
        JsonElement element = JsonSerializer.SerializeToElement(json);
        if (corruption == "duplicate-property")
            element = JsonDocument.Parse(element.GetRawText().Replace("\"contentRevision\":", "\"contentRevision\":4,\"contentRevision\":", StringComparison.Ordinal)).RootElement.Clone();
        request = request with { WorkspaceSnapshot = element, WorkspaceSnapshotDigest = InstallLinkedWorkspaceSnapshotTransfer.ComputeDigest(element) };
        if (corruption == "digest") request = request with { WorkspaceSnapshotDigest = new string('f', 64) };
        if (corruption == "missing-digest") request = request with { WorkspaceSnapshotDigest = null };
        if (corruption == "missing-snapshot") request = request with { WorkspaceSnapshot = null };
        Assert.Equal(StatusCodes.Status400BadRequest, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.UpsertForInstallation(fixture.Installation, request, initial.RemoteRevision, initial.ServerToken)).StatusCode);
        var unchanged = Assert.Single(fixture.Service.ListForInstallation(fixture.Installation));
        Assert.Equal(initial.ServerToken, unchanged.ServerToken);
        Assert.Equal(initial.WorkspaceSnapshotDigest, unchanged.WorkspaceSnapshotDigest);
    }

    [Fact]
    public void Reviewed_payload_only_client_cannot_erase_wizard_state()
    {
        using Fixture fixture = new();
        var first = fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(SampleSnapshot()), 0);
        Assert.Equal(StatusCodes.Status409Conflict, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.UpsertForInstallation(fixture.Installation,
                first with { WorkspaceSnapshot = null, WorkspaceSnapshotDigest = null }, first.RemoteRevision, first.ServerToken)).StatusCode);
        Assert.Equal(first.WorkspaceSnapshotDigest,
            Assert.Single(fixture.Service.ListForInstallation(fixture.Installation)).WorkspaceSnapshotDigest);
    }

    [Fact]
    public void Full_snapshot_upgrade_and_auxiliary_only_change_are_real_CAS_mutations()
    {
        using Fixture fixture = new();
        var full = ToRecord(SampleSnapshot());
        var legacy = fixture.Service.UpsertForInstallation(fixture.Installation,
            full with { WorkspaceSnapshot = null, WorkspaceSnapshotDigest = null }, 0);
        var upgraded = fixture.Service.UpsertForInstallation(fixture.Installation, full, legacy.RemoteRevision, legacy.ServerToken);
        Assert.Equal(2, upgraded.RemoteRevision);
        var core = SampleSnapshot();
        var changed = core with { ContentRevision = core.ContentRevision + 1, Document = core.Document with
            { State = core.Document.State with { AuxiliaryState = core.Document.AuxiliaryState with
                { CharacterCreationSkillsReceipts = null } } } };
        var next = fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(changed), upgraded.RemoteRevision, upgraded.ServerToken);
        Assert.Equal(upgraded.Payload, next.Payload);
        Assert.Equal(3, next.RemoteRevision);
        Assert.NotEqual(upgraded.WorkspaceSnapshotDigest, next.WorkspaceSnapshotDigest);
        Assert.Equal(StatusCodes.Status409Conflict, Assert.Throws<InstallLinkingOperationException>(() =>
            fixture.Service.UpsertForInstallation(fixture.Installation, full, upgraded.RemoteRevision, upgraded.ServerToken)).StatusCode);
    }

    [Fact]
    public void Corrupt_persisted_snapshot_is_not_projected_as_valid()
    {
        using Fixture fixture = new();
        fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(SampleSnapshot()), 0);
        string path = fixture.Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!;
        JsonObject store = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        store["snapshots"]![0]!["workspaceSnapshot"]!["contentRevision"] = 900;
        File.WriteAllText(path, store.ToJsonString());
        var reloaded = new InstallLinkedWorkspaceSnapshotService(new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
        Assert.Equal(StatusCodes.Status503ServiceUnavailable,
            Assert.Throws<InstallLinkingOperationException>(() => reloaded.ListForInstallation(fixture.Installation)).StatusCode);
    }

    [Fact]
    public void Duplicate_persisted_identity_fails_closed_instead_of_selecting_last_row()
    {
        using Fixture fixture = new();
        fixture.Service.UpsertForInstallation(fixture.Installation, ToRecord(SampleSnapshot()), 0);
        string path = fixture.Configuration["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"]!;
        JsonObject store = JsonNode.Parse(File.ReadAllText(path))!.AsObject();
        var rows = store["snapshots"]!.AsArray();
        rows.Add(rows[0]!.DeepClone());
        File.WriteAllText(path, store.ToJsonString());
        Assert.Throws<InvalidDataException>(() => new InstallLinkedWorkspaceSnapshotStore(fixture.Configuration));
    }

    internal static WorkspaceDocumentSnapshot SampleSnapshot()
    {
        var id = new CharacterWorkspaceId("ws-transfer");
        // Transport fixtures, deliberately not claims of rule-valid receipts.
        var draft = new CharacterCreationFoundationDraftLedger("fixture/v1", id, 3, 4,
            new string('a', 64), new string('b', 64), "Human", new("street", "v1"), [], [],
            new Dictionary<string, string> { ["story"] = "Straßenkind — live choice", ["Story"] = "distinct case-sensitive key", ["language"] = "de" },
            ["anchor-1"], "review", false, new string('c', 64));
        var auxiliary = new WorkspaceDocumentAuxiliaryState(CharacterCreationFoundationDraft: draft,
            CharacterCreationSkillsReceipts: [],
            CharacterCreationFinalizationArchive: new(new(CharacterCreationFoundationDraft: draft)));
        return new(id, new WorkspaceDocument(new WorkspaceDocumentState("sr5", 1, "workspace", "<character><name>Runner</name></character>")
            { AuxiliaryState = auxiliary }), new DateTimeOffset(2026, 9, 9, 12, 0, 0, TimeSpan.Zero), 7, 5);
    }

    // Large text only exercises transport bounds; it is not a rule-valid draft.
    private static WorkspaceDocumentSnapshot SnapshotWithFoundationTransportText(string story)
    {
        var core = SampleSnapshot();
        var draft = core.Document.AuxiliaryState.CharacterCreationFoundationDraft!;
        var values = new Dictionary<string, string>(draft.FollowUpValues, StringComparer.Ordinal) { ["story"] = story };
        return core with { Document = core.Document with { State = core.Document.State with
            { AuxiliaryState = core.Document.AuxiliaryState with
                { CharacterCreationFoundationDraft = draft with { FollowUpValues = values } } } } };
    }

    internal static InstallLinkedWorkspaceSnapshotRecord ToRecord(WorkspaceDocumentSnapshot core)
    {
        JsonElement json = InstallLinkedWorkspaceSnapshotTransfer.Encode(core);
        return new("", core.Id.Value, core.Document.RulesetId, "NativeXml", core.Document.SchemaVersion,
            core.Document.PayloadKind, core.Document.Content, core.LastUpdatedUtc, "ins-transfer",
            "Runner", "Runner", "Human", "Priority", "5", "6", 0, 0, false,
            WorkspaceSnapshot: json, WorkspaceSnapshotDigest: InstallLinkedWorkspaceSnapshotTransfer.ComputeDigest(json));
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), "chummer-snapshot-transfer-tests", Guid.NewGuid().ToString("N"));
        public Fixture()
        {
            Configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
            { ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = Path.Combine(_root, "snapshots.json") }).Build();
            Service = new(new InstallLinkedWorkspaceSnapshotStore(Configuration));
        }
        public IConfiguration Configuration { get; }
        public InstallLinkedWorkspaceSnapshotService Service { get; }
        public ClaimedInstallationDto Installation { get; } = new(
            "ins-transfer", "fixture", "internal", "fixture", "account_required", "active",
            DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, UserId: "user", SubjectId: "subject");
        public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
    }
}
