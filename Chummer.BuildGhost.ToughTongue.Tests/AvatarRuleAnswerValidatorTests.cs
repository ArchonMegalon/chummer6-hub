using Chummer.Run.Api.Services.Avatar;
using Chummer.Run.Contracts.Avatar;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class AvatarRuleAnswerValidatorTests
{
    [TestMethod]
    public void ExactResolvedAnswerIsAccepted()
    {
        AvatarRuleAuthorityRequest request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request);

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

        Assert.IsEmpty(failures, string.Join(',', failures));
    }

    [TestMethod]
    public void UnknownDirectApplyActionAndDigestRewriteAreRejected()
    {
        AvatarRuleAuthorityRequest request = Request();
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
        AvatarRuleAuthorityRequest request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            WorkspaceRevision = request.WorkspaceRevision - 1,
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
        AvatarRuleAuthorityRequest request = Request();
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
        AvatarRuleAuthorityRequest request = Request();
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
        AvatarRuleAuthorityRequest request = Request();
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
        AvatarRuleAuthorityRequest request = Request();
        AvatarSourceAnchor inventedRoute = ValidAnswer(request).SourceAnchors[0] with
        {
            LocalSourceRoute = "chummer://sources/sr5-core?page=175&apply=1"
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
        AvatarRuleAuthorityRequest request = Request();
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
        AvatarRuleAuthorityRequest request = Request();

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

    private static AvatarRuleAuthorityRequest Request()
        => new(
            AvatarGatewayContractVersions.RuleAuthorityRequestV1,
            "owner-1",
            "workspace-1",
            417,
            "character-1",
            "campaign-1",
            "sr5",
            Sha('a'),
            Sha('b'),
            Sha('c'),
            Sha('d'),
            Sha('e'),
            "de-AT",
            "Wie berechnet sich mein Rückstoßausgleich?",
            "recoil");

    private static AvatarRuleAnswerEnvelope ValidAnswer(AvatarRuleAuthorityRequest request)
    {
        AvatarSourceAnchor anchor = new(
            "anchor-recoil-1",
            "sr5-core",
            "Shadowrun 5 Grundregelwerk",
            175,
            "combat.recoil.compensation",
            "chummer://sources/sr5-core?page=175");
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
            request.WorkspaceRevision,
            request.RuntimeFingerprint,
            request.SourceDigest,
            string.Empty,
            null);
        return unsigned with { AnswerDigest = AvatarRuleAnswerDigest.Compute(unsigned) };
    }

    private static string Sha(char value) => "sha256:" + new string(value, 64);
}
