using Chummer.Run.Api.Services.Avatar;
using Chummer.Run.Contracts.Avatar;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class AvatarRuleAnswerValidatorTests
{
    [TestMethod]
    public void ExactResolvedAnswerIsAccepted()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request);

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        Assert.IsEmpty(failures, string.Join(',', failures));
    }

    [TestMethod]
    public void UnknownDirectApplyActionAndDigestRewriteAreRejected()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            AllowedActions =
            [
                new AvatarAllowedAction(
                    "apply-character-directly",
                    "chummer.apply_character",
                    "chummer://workspace/ws-1/apply",
                    false)
            ]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        CollectionAssert.Contains(failures.ToArray(), "action-type-forbidden");
    }

    [TestMethod]
    public void StaleWorkspaceAndInventedAnchorReferenceAreRejected()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            WorkspaceRevision = request.Request.ExpectedBinding.WorkspaceRevision - 1,
            CalculationSteps =
            [
                new AvatarCalculationStep("step-1", "Agility + skill", "12 dice", ["invented-page-999"])
            ]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        CollectionAssert.Contains(failures.ToArray(), "workspace-revision-drift");
        CollectionAssert.Contains(failures.ToArray(), "calculation-anchor-reference-invalid");
    }

    [TestMethod]
    public void Open_source_action_must_reference_an_exact_current_anchor()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            AllowedActions =
            [
                new AvatarAllowedAction(
                    "open-invented-rule",
                    AvatarGatewayActionTypes.OpenRuleSource,
                    "chummer://sources/invented?page=999",
                    false)
            ]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        CollectionAssert.Contains(failures.ToArray(), "action-source-route-unbound");
    }

    [TestMethod]
    public void Workbench_action_cannot_disguise_a_mutation_route()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            AllowedActions =
            [
                new AvatarAllowedAction(
                    "open-workbench",
                    AvatarGatewayActionTypes.OpenWorkbenchRoute,
                    "chummer://workspace/ws-1/apply",
                    false)
            ]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        CollectionAssert.Contains(failures.ToArray(), "action-workbench-route-invalid");
    }

    [TestMethod]
    public void Only_the_exact_read_only_workbench_template_is_accepted()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            AllowedActions =
            [
                new AvatarAllowedAction(
                    "open-workbench",
                    AvatarGatewayActionTypes.OpenWorkbenchRoute,
                    "chummer://workspace/workspace-1/build-ghost/workbench",
                    false)
            ]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        Assert.IsEmpty(failures, string.Join(',', failures));
    }

    [TestMethod]
    public void Source_route_is_bound_to_exact_source_and_page_query_only()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarSourceAnchor inventedRoute = ValidAnswer(request).SourceAnchors[0] with
        {
            LocalSourceRoute = "chummer://sources/sr6-core?page=41&apply=1"
        };
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            SourceAnchors = [inventedRoute],
            AllowedActions =
            [
                new AvatarAllowedAction(
                    "open-rule",
                    AvatarGatewayActionTypes.OpenRuleSource,
                    inventedRoute.LocalSourceRoute,
                    false)
            ]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        CollectionAssert.Contains(failures.ToArray(), "source-route-invalid");
    }

    [TestMethod]
    public void Malformed_null_packet_members_are_rejected_without_throwing()
    {
        AvatarRuleAuthorityInvocation request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            SourceAnchors = [null!],
            AnswerDigest = Sha('f')
        };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        CollectionAssert.Contains(failures.ToArray(), "source-anchor-null");
        CollectionAssert.Contains(failures.ToArray(), "answer-digest-invalid");
    }

    [TestMethod]
    public void SafeUnavailableEnvelopeIsBoundAndValid()
    {
        AvatarRuleAuthorityInvocation request = Request();

        AvatarRuleAnswerEnvelope answer = AvatarRuleAnswerValidator.SafeUnavailable(request);
        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        Assert.AreEqual(AvatarGatewayStatuses.Unavailable, answer.Status);
        Assert.IsEmpty(failures, string.Join(',', failures));
        StringAssert.StartsWith(answer.AnswerDigest, "sha256:");
    }

    [TestMethod]
    public void AuthorityEndpointRequiresExactChummerHttpsRoute()
    {
        Uri accepted = AvatarRuleAuthorityClient.ResolveEndpoint(
            "https://core.chummer.run/api/internal/avatar-rule-authority/resolve");
        Assert.AreEqual("core.chummer.run", accepted.Host);

        Assert.ThrowsExactly<AvatarRuleAuthorityException>(() =>
            AvatarRuleAuthorityClient.ResolveEndpoint(
                "https://evil.example/api/internal/avatar-rule-authority/resolve"));
        Assert.ThrowsExactly<AvatarRuleAuthorityException>(() =>
            AvatarRuleAuthorityClient.ResolveEndpoint(
                "https://core.chummer.run/api/internal/avatar-rule-authority/resolve?leak=true"));
    }

    [TestMethod]
    public void Core_wire_request_contains_only_typed_authority_and_exact_binding()
    {
        AvatarRuleAuthorityInvocation invocation = Request();

        string json = JsonSerializer.Serialize(
            invocation.Request,
            new JsonSerializerOptions(JsonSerializerDefaults.Web));

        StringAssert.Contains(json, "\"contractVersion\":\"chummer.avatar-rule-authority/v1\"");
        StringAssert.Contains(json, "\"intentId\":\"rules.session.quick-actions\"");
        StringAssert.Contains(json, "\"profileId\":\"official.sr6.core\"");
        StringAssert.Contains(json, "\"sourceDigest\":\"sha256:");
        Assert.IsFalse(json.Contains("question", StringComparison.OrdinalIgnoreCase));
        Assert.IsFalse(json.Contains("ownerId", StringComparison.Ordinal));
        Assert.IsFalse(json.Contains("workspaceId", StringComparison.Ordinal));
        Assert.IsFalse(json.Contains("characterId", StringComparison.Ordinal));
    }

    private static AvatarRuleAuthorityInvocation Request()
        => new(
            new AvatarRuleAuthorityRequest(
                AvatarGatewayContractVersions.RuleAuthorityV1,
                AvatarRuleIntentAdapter.SupportedIntentId,
                AvatarRuleIntentAdapter.SupportedIntentVersion,
                AvatarRuleIntentAdapter.SupportedCapabilityId,
                AvatarRuleIntentAdapter.SupportedInvocationKind,
                "session-actions",
                [],
                new AvatarRuleAuthorityBinding(
                    AvatarRuleIntentAdapter.SupportedRulesetId,
                    Sha('a'),
                    AvatarRuleIntentAdapter.SupportedRulesetProfileId,
                    417,
                    Sha('b'),
                    Sha('c'),
                    Sha('d'),
                    Sha('e'))),
            "workspace-1",
            "de-AT");

    private static AvatarRuleAnswerEnvelope ValidAnswer(AvatarRuleAuthorityInvocation request)
    {
        AvatarSourceAnchor anchor = new(
            "anchor-recoil-1",
            "sr6-core",
            "Shadowrun Sixth World Core Rulebook",
            41,
            "session.quick-actions",
            "chummer://sources/sr6-core?page=41");
        AvatarRuleAnswerEnvelope unsigned = new(
            AvatarGatewayContractVersions.RuleAnswerV1,
            AvatarGatewayStatuses.Resolved,
            "Dein Rückstoßausgleich beträgt aktuell drei Punkte.",
            "Rückstoßausgleich: 3.",
            [new AvatarCalculationStep("step-1", "Basis + Ausrüstung", "3", [anchor.AnchorId])],
            [],
            true,
            [anchor],
            [new AvatarAllowedAction("open-rule-recoil", AvatarGatewayActionTypes.OpenRuleSource, anchor.LocalSourceRoute, false)],
            request.Request.ExpectedBinding.WorkspaceRevision,
            request.Request.ExpectedBinding.RuntimeFingerprint,
            request.Request.ExpectedBinding.SourceDigest,
            string.Empty,
            null);
        return unsigned with { AnswerDigest = AvatarRuleAnswerDigest.Compute(unsigned) };
    }

    private static string Sha(char value) => "sha256:" + new string(value, 64);
}
