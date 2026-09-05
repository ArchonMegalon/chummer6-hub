using Chummer.Run.AI.Services.Avatar;
using Chummer.Run.Contracts.Avatar;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class AvatarRuleAnswerValidatorTests
{
    private const string CorePackageDigest = "sha256:9999999999999999999999999999999999999999999999999999999999999999";

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
    public void Answer_is_bound_to_the_exact_question_and_gateway_operation()
    {
        AvatarRuleAuthorityRequest original = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(original);
        AvatarRuleAuthorityRequest differentUnsigned = original with
        {
            Question = "How much karma remains?",
            GatewayOperationDigest = Sha('9'),
            RequestDigest = string.Empty
        };
        AvatarRuleAuthorityRequest different = differentUnsigned with
        {
            RequestDigest = AvatarRuleAuthorityRequestDigest.Compute(differentUnsigned)
        };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, different);

        CollectionAssert.Contains(failures.ToArray(), "authority-request-digest-drift");
    }

    [TestMethod]
    public void Answer_is_bound_to_the_exact_resealed_core_package_authority()
    {
        AvatarRuleAuthorityRequest original = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(original);
        AvatarRuleAuthorityRequest differentUnsigned = original with
        {
            CorePackageDigest = Sha('8'),
            RequestDigest = string.Empty
        };
        AvatarRuleAuthorityRequest different = differentUnsigned with
        {
            RequestDigest = AvatarRuleAuthorityRequestDigest.Compute(differentUnsigned)
        };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, different);

        CollectionAssert.Contains(failures.ToArray(), "authority-request-digest-drift");
    }

    [TestMethod]
    public void Every_resolved_calculation_step_requires_a_current_source_anchor()
    {
        AvatarRuleAuthorityRequest request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request) with
        {
            CalculationSteps = [new AvatarCalculationStep("step-1", "Agility + skill", "12 dice", [])]
        };
        answer = answer with { AnswerDigest = AvatarRuleAnswerDigest.Compute(answer) };

        IReadOnlyList<string> failures = AvatarRuleAnswerValidator.Validate(answer, request);

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

    [TestMethod]
    public async Task Authority_client_rejects_non_json_and_duplicate_property_responses()
    {
        AvatarRuleAuthorityRequest request = Request();
        AvatarRuleAnswerEnvelope answer = ValidAnswer(request);
        string validJson = JsonSerializer.Serialize(answer);
        string duplicateJson = validJson.Insert(1, $"\"status\":\"{AvatarGatewayStatuses.Resolved}\",");

        AvatarRuleAuthorityException nonJson = await InvokeInvalidResponse(
            request,
            "not-json",
            "text/plain");
        AvatarRuleAuthorityException duplicate = await InvokeInvalidResponse(
            request,
            duplicateJson,
            "application/json");

        Assert.AreEqual("avatar-rule-authority-content-type-invalid", nonJson.Reason);
        Assert.AreEqual("avatar-rule-authority-response-invalid", duplicate.Reason);
    }

    [TestMethod]
    public async Task Authority_client_fails_closed_without_exact_resealed_core_binding()
    {
        AvatarRuleAuthorityRequest request = Request();
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(
            new Dictionary<string, string?>
            {
                [AvatarRuleAuthorityClient.EndpointConfigurationKey] =
                    "https://core.chummer.run/api/internal/avatar-rule-authority/resolve",
                [AvatarRuleAuthorityClient.ServiceTokenConfigurationKey] =
                    "authority-token-abcdefghijklmnopqrstuvwxyz-123456"
            }).Build();
        using HttpClient http = new(new ThrowIfCalledHandler());
        AvatarRuleAuthorityClient client = new(http, configuration);

        AvatarRuleAuthorityException exception = await Assert.ThrowsExactlyAsync<AvatarRuleAuthorityException>(
            () => client.ResolveAsync(request, CancellationToken.None));

        Assert.IsNull(client.Binding);
        Assert.AreEqual("avatar-rule-authority-request-binding-invalid", exception.Reason);
    }

    private static async Task<AvatarRuleAuthorityException> InvokeInvalidResponse(
        AvatarRuleAuthorityRequest request,
        string body,
        string mediaType)
    {
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(
            new Dictionary<string, string?>
            {
                [AvatarRuleAuthorityClient.EndpointConfigurationKey] =
                    "https://core.chummer.run/api/internal/avatar-rule-authority/resolve",
                [AvatarRuleAuthorityClient.ServiceTokenConfigurationKey] =
                    "authority-token-abcdefghijklmnopqrstuvwxyz-123456",
                [AvatarRuleAuthorityClient.CoreContractConfigurationKey] =
                    AvatarGatewayContractVersions.CoreTypedRuleAuthorityV1,
                [AvatarRuleAuthorityClient.CorePackageIdConfigurationKey] = "Chummer.Engine.Contracts",
                [AvatarRuleAuthorityClient.CorePackageVersionConfigurationKey] = "6.0.0-avatar-authority.1",
                [AvatarRuleAuthorityClient.CorePackageDigestConfigurationKey] = CorePackageDigest
            }).Build();
        using HttpClient http = new(new StaticResponseHandler(body, mediaType));
        AvatarRuleAuthorityClient client = new(http, configuration);
        try
        {
            await client.ResolveAsync(request, CancellationToken.None);
        }
        catch (AvatarRuleAuthorityException exception)
        {
            return exception;
        }

        Assert.Fail("The authority client accepted an invalid response.");
        throw new InvalidOperationException("unreachable");
    }

    private static AvatarRuleAuthorityRequest Request()
    {
        AvatarRuleAuthorityRequest unsigned = new(
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
            Sha('f'),
            AvatarGatewayContractVersions.CoreTypedRuleAuthorityV1,
            "Chummer.Engine.Contracts",
            "6.0.0-avatar-authority.1",
            CorePackageDigest,
            "de-AT",
            "Wie berechnet sich mein Rückstoßausgleich?",
            "recoil",
            string.Empty);
        return unsigned with
        {
            RequestDigest = AvatarRuleAuthorityRequestDigest.Compute(unsigned)
        };
    }

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
            request.RequestDigest,
            string.Empty,
            null);
        return unsigned with { AnswerDigest = AvatarRuleAnswerDigest.Compute(unsigned) };
    }

    private static string Sha(char value) => "sha256:" + new string(value, 64);

    private sealed class StaticResponseHandler(string body, string mediaType) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            HttpResponseMessage response = new(HttpStatusCode.OK)
            {
                Content = new StringContent(body, Encoding.UTF8)
            };
            response.Content.Headers.ContentType = new MediaTypeHeaderValue(mediaType)
            {
                CharSet = "utf-8"
            };
            return Task.FromResult(response);
        }
    }


    private sealed class ThrowIfCalledHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => throw new AssertFailedException("HTTP authority was called without a Core authority binding.");
    }
}
