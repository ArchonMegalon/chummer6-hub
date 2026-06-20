using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Control.Contracts.Support;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Support;

public sealed record SupportProgressEmailDispatchResult(
    string StageId,
    string State,
    string Recipient,
    string FromEmail,
    string Subject,
    string Provider,
    DateTimeOffset OccurredAtUtc,
    string? DeliveryId = null,
    string? AwardKey = null,
    string? AwardLabel = null,
    string? DecisionOutcome = null,
    string? ImplementationPosture = null,
    string? Reason = null,
    string? EtaText = null,
    string? DownloadUrl = null,
    string? InstallRailUrl = null,
    string? Error = null);

public sealed class SupportProgressEmailWorkflowService
{
    private const string DefaultEaBaseUrl = "http://127.0.0.1:8090";
    private const string DefaultEmailitBaseUrl = "https://api.emailit.com/v2";
    private const string DefaultPublicBaseUrl = "https://chummer.run";
    private const string DefaultFromEmail = "wageslave@chummer.run";
    private const string DefaultFromName = "Wageslave";
    private const string DefaultReplyTo = "support@chummer.run";
    private const string ConnectorDispatchTool = "connector.dispatch";
    private const string DeliverySendAction = "delivery.send";
    private const string EmailChannel = "email";
    private const string EmailitProvider = "emailit";

    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<SupportProgressEmailWorkflowService> _logger;

    public SupportProgressEmailWorkflowService(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<SupportProgressEmailWorkflowService>? logger = null)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger ?? NullLogger<SupportProgressEmailWorkflowService>.Instance;
    }

    public SupportProgressEmailDispatchResult SendRequestReceived(SupportCaseProjection supportCase)
    {
        ArgumentNullException.ThrowIfNull(supportCase);
        return Dispatch(
            supportCase,
            stageId: "request_received",
            subject: $"Chummer received your request: {supportCase.Title}",
            content: BuildRequestReceivedContent(supportCase),
            awardKey: null,
            awardLabel: null,
            decisionOutcome: null,
            implementationPosture: null,
            reason: null,
            etaText: null,
            downloadUrl: null,
            installRailUrl: null);
    }

    public SupportProgressEmailDispatchResult SendAuditedDecision(
        SupportCaseProjection supportCase,
        SupportCaseTransitionRequest request)
    {
        ArgumentNullException.ThrowIfNull(supportCase);
        ArgumentNullException.ThrowIfNull(request);

        string targetStatus = (request.TargetStatus ?? string.Empty).Trim().ToLowerInvariant();
        string decisionOutcome = NormalizeDecisionOutcome(request.DecisionOutcome, targetStatus);
        string implementationPosture = NormalizeImplementationPosture(request.ImplementationPosture, targetStatus);
        string reason = NormalizeOptional(request.DecisionReason, 160)
            ?? NormalizeOptional(request.Note, 160)
            ?? DefaultDecisionReason(targetStatus);
        string etaText = NormalizeOptional(request.EtaText, 80) ?? DefaultEtaText(targetStatus);
        var (awardKey, awardLabel) = ResolveAward(decisionOutcome, implementationPosture);
        string subject = decisionOutcome == "approved"
            ? $"Chummer approved your request: {supportCase.Title}"
            : $"Chummer closed your request: {supportCase.Title}";

        return Dispatch(
            supportCase,
            stageId: "audited_decision",
            subject: subject,
            content: BuildAuditedDecisionContent(
                supportCase,
                decisionOutcome,
                implementationPosture,
                reason,
                etaText,
                awardLabel),
            awardKey: awardKey,
            awardLabel: awardLabel,
            decisionOutcome: decisionOutcome,
            implementationPosture: implementationPosture,
            reason: reason,
            etaText: etaText,
            downloadUrl: null,
            installRailUrl: null);
    }

    public SupportProgressEmailDispatchResult SendFixAvailable(
        SupportCaseProjection supportCase,
        SupportCaseNotificationRequest request)
    {
        ArgumentNullException.ThrowIfNull(supportCase);
        ArgumentNullException.ThrowIfNull(request);

        string downloadUrl = NormalizeOptional(request.DownloadUrl, 400)
            ?? $"{ResolvePublicBaseUrl()}/downloads";
        string? installRailUrl = HasInstallRailContext(supportCase)
            ? $"{ResolvePublicBaseUrl()}/account/access"
            : null;

        return Dispatch(
            supportCase,
            stageId: "fix_available",
            subject: $"Chummer fix available now: {supportCase.Title}",
            content: BuildFixAvailableContent(supportCase, request, downloadUrl, installRailUrl),
            awardKey: null,
            awardLabel: null,
            decisionOutcome: null,
            implementationPosture: null,
            reason: NormalizeOptional(request.Note, 160),
            etaText: null,
            downloadUrl: downloadUrl,
            installRailUrl: installRailUrl);
    }

    private SupportProgressEmailDispatchResult Dispatch(
        SupportCaseProjection supportCase,
        string stageId,
        string subject,
        string content,
        string? awardKey,
        string? awardLabel,
        string? decisionOutcome,
        string? implementationPosture,
        string? reason,
        string? etaText,
        string? downloadUrl,
        string? installRailUrl)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        string recipient = NormalizeOptional(supportCase.ReporterEmail, 256) ?? string.Empty;
        string fromEmail = ResolveFromEmail();
        string fromName = ResolveFromName();

        if (!IsEnabled())
        {
            return BuildSkipped(
                stageId,
                recipient,
                fromEmail,
                subject,
                awardKey,
                awardLabel,
                decisionOutcome,
                implementationPosture,
                reason,
                etaText,
                downloadUrl,
                installRailUrl,
                "workflow_disabled",
                now);
        }

        if (string.IsNullOrWhiteSpace(recipient))
        {
            return BuildSkipped(
                stageId,
                recipient,
                fromEmail,
                subject,
                awardKey,
                awardLabel,
                decisionOutcome,
                implementationPosture,
                reason,
                etaText,
                downloadUrl,
                installRailUrl,
                "reporter_email_missing",
                now);
        }

        string eaApiToken = (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_API_TOKEN"] ?? string.Empty).Trim();
        string principalId = (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_PRINCIPAL_ID"] ?? string.Empty).Trim();
        string bindingId = (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BINDING_ID"] ?? string.Empty).Trim();
        string emailitApiKey = (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_API_KEY"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(eaApiToken)
            || string.IsNullOrWhiteSpace(principalId)
            || string.IsNullOrWhiteSpace(bindingId)
            || string.IsNullOrWhiteSpace(emailitApiKey))
        {
            return BuildFailed(
                stageId,
                recipient,
                fromEmail,
                subject,
                awardKey,
                awardLabel,
                decisionOutcome,
                implementationPosture,
                reason,
                etaText,
                downloadUrl,
                installRailUrl,
                "workflow_unconfigured",
                now);
        }

        string idempotencyKey = BuildIdempotencyKey(supportCase, stageId);
        string? deliveryId = null;
        try
        {
            deliveryId = QueueDelivery(
                principalId: principalId,
                bindingId: bindingId,
                recipient: recipient,
                stageId: stageId,
                subject: subject,
                content: content,
                supportCase: supportCase,
                awardKey: awardKey,
                awardLabel: awardLabel,
                decisionOutcome: decisionOutcome,
                implementationPosture: implementationPosture,
                reason: reason,
                etaText: etaText,
                downloadUrl: downloadUrl,
                installRailUrl: installRailUrl,
                idempotencyKey: idempotencyKey,
                fromEmail: fromEmail,
                fromName: fromName);

            string providerMessageId = SendEmailit(
                recipient: recipient,
                subject: subject,
                content: content,
                supportCase: supportCase,
                stageId: stageId,
                deliveryId: deliveryId,
                awardLabel: awardLabel,
                idempotencyKey: idempotencyKey,
                apiKey: emailitApiKey,
                fromEmail: fromEmail,
                fromName: fromName);

            MarkSent(
                principalId: principalId,
                deliveryId: deliveryId,
                recipient: recipient,
                subject: subject,
                stageId: stageId,
                providerMessageId: providerMessageId,
                fromEmail: fromEmail);

            return new SupportProgressEmailDispatchResult(
                StageId: stageId,
                State: "sent",
                Recipient: recipient,
                FromEmail: fromEmail,
                Subject: subject,
                Provider: EmailitProvider,
                OccurredAtUtc: now,
                DeliveryId: deliveryId,
                AwardKey: awardKey,
                AwardLabel: awardLabel,
                DecisionOutcome: decisionOutcome,
                ImplementationPosture: implementationPosture,
                Reason: reason,
                EtaText: etaText,
                DownloadUrl: downloadUrl,
                InstallRailUrl: installRailUrl,
                Error: null);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Support progress email stage {StageId} failed for support case {CaseId}.", stageId, supportCase.CaseId);
            if (!string.IsNullOrWhiteSpace(deliveryId))
            {
                TryMarkFailed(principalId, deliveryId, ex.Message);
            }

            return BuildFailed(
                stageId,
                recipient,
                fromEmail,
                subject,
                awardKey,
                awardLabel,
                decisionOutcome,
                implementationPosture,
                reason,
                etaText,
                downloadUrl,
                installRailUrl,
                ex.Message,
                now,
                deliveryId);
        }
    }

    private string QueueDelivery(
        string principalId,
        string bindingId,
        string recipient,
        string stageId,
        string subject,
        string content,
        SupportCaseProjection supportCase,
        string? awardKey,
        string? awardLabel,
        string? decisionOutcome,
        string? implementationPosture,
        string? reason,
        string? etaText,
        string? downloadUrl,
        string? installRailUrl,
        string idempotencyKey,
        string fromEmail,
        string fromName)
    {
        var metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
        {
            ["stage_id"] = stageId,
            ["case_id"] = supportCase.CaseId,
            ["from_email"] = fromEmail,
            ["from_name"] = fromName,
            ["reply_to"] = ResolveReplyTo(),
            ["subject"] = subject,
        };
        AddMetadataIfValue(metadata, "award_key", awardKey);
        AddMetadataIfValue(metadata, "award_label", awardLabel);
        AddMetadataIfValue(metadata, "decision_outcome", decisionOutcome);
        AddMetadataIfValue(metadata, "implementation_posture", implementationPosture);
        AddMetadataIfValue(metadata, "reason", reason);
        AddMetadataIfValue(metadata, "eta_text", etaText);
        AddMetadataIfValue(metadata, "download_url", downloadUrl);
        AddMetadataIfValue(metadata, "install_rail_url", installRailUrl);
        AddMetadataIfValue(metadata, "installation_id", supportCase.InstallationId);
        AddMetadataIfValue(metadata, "application_version", supportCase.ApplicationVersion);
        AddMetadataIfValue(metadata, "release_channel", supportCase.ReleaseChannel);
        AddMetadataIfValue(metadata, "head_id", supportCase.HeadId);
        AddMetadataIfValue(metadata, "platform", supportCase.Platform);
        AddMetadataIfValue(metadata, "arch", supportCase.Arch);
        AddMetadataIfValue(metadata, "fixed_version", supportCase.FixedVersion);
        AddMetadataIfValue(metadata, "fixed_channel", supportCase.FixedChannel);

        var payload = new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = EmailChannel,
                recipient,
                subject,
                content,
                metadata,
                idempotency_key = idempotencyKey,
            }
        };

        JsonObject response = SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEaBaseUrl()}/v1/tools/execute",
            payload: payload,
            bearerToken: ResolveEaApiToken(),
            principalId: principalId);
        string deliveryId = response["target_ref"]?.GetValue<string>()
            ?? response["output_json"]?["delivery_id"]?.GetValue<string>()
            ?? string.Empty;
        if (string.IsNullOrWhiteSpace(deliveryId))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        return deliveryId;
    }

    private string SendEmailit(
        string recipient,
        string subject,
        string content,
        SupportCaseProjection supportCase,
        string stageId,
        string deliveryId,
        string? awardLabel,
        string idempotencyKey,
        string apiKey,
        string fromEmail,
        string fromName)
    {
        var payload = new
        {
            from = $"{fromName} <{fromEmail}>",
            to = recipient,
            subject,
            text = content,
            html = $"<pre>{EscapeHtml(content)}</pre>",
            reply_to = ResolveReplyTo(),
            tracking = false,
            meta = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
            {
                ["delivery_id"] = deliveryId,
                ["stage_id"] = stageId,
                ["case_id"] = supportCase.CaseId,
                ["provider"] = EmailitProvider,
                ["award_label"] = awardLabel ?? string.Empty,
            }
        };

        JsonObject response = SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEmailitBaseUrl()}/emails",
            payload: payload,
            bearerToken: apiKey,
            principalId: null,
            idempotencyKey: idempotencyKey);

        return response["id"]?.GetValue<string>()
            ?? response["data"]?["id"]?.GetValue<string>()
            ?? deliveryId;
    }

    private void MarkSent(
        string principalId,
        string deliveryId,
        string recipient,
        string subject,
        string stageId,
        string providerMessageId,
        string fromEmail)
    {
        var payload = new
        {
            receipt_json = new
            {
                transport = EmailitProvider,
                provider = EmailitProvider,
                state = "sent",
                delivery_id = deliveryId,
                stage_id = stageId,
                recipient,
                from_email = fromEmail,
                subject,
                provider_message_id = providerMessageId,
            }
        };

        SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEaBaseUrl()}/v1/delivery/outbox/{Uri.EscapeDataString(deliveryId)}/sent",
            payload: payload,
            bearerToken: ResolveEaApiToken(),
            principalId: principalId);
    }

    private void TryMarkFailed(string principalId, string deliveryId, string error)
    {
        try
        {
            SendJson(
                method: HttpMethod.Post,
                url: $"{ResolveEaBaseUrl()}/v1/delivery/outbox/{Uri.EscapeDataString(deliveryId)}/failed",
                payload: new
                {
                    error = Truncate(error, 1000),
                    retry_in_seconds = 60,
                    dead_letter = false,
                },
                bearerToken: ResolveEaApiToken(),
                principalId: principalId);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to mark support progress email delivery {DeliveryId} as failed.", deliveryId);
        }
    }

    private JsonObject SendJson(
        HttpMethod method,
        string url,
        object payload,
        string bearerToken,
        string? principalId,
        string? idempotencyKey = null)
    {
        using var request = new HttpRequestMessage(method, url);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (!string.IsNullOrWhiteSpace(bearerToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearerToken);
        }

        if (!string.IsNullOrWhiteSpace(principalId))
        {
            request.Headers.Add("x-ea-principal-id", principalId);
        }

        if (!string.IsNullOrWhiteSpace(idempotencyKey))
        {
            request.Headers.Add("Idempotency-Key", idempotencyKey);
        }

        request.Content = JsonContent.Create(payload);
        using var response = _httpClient.SendAsync(request).GetAwaiter().GetResult();
        string body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(body, 600)}");
        }

        if (string.IsNullOrWhiteSpace(body))
        {
            return new JsonObject();
        }

        return JsonNode.Parse(body)?.AsObject() ?? new JsonObject();
    }

    private static string BuildRequestReceivedContent(SupportCaseProjection supportCase)
        => string.Join(
            "\n",
            new[]
            {
                "Your request is in.",
                $"Case: {supportCase.Title}",
                $"Case ID: {supportCase.CaseId}",
                $"Kind: {supportCase.Kind}",
                $"Owner lane: {supportCase.CandidateOwnerRepo}",
                "",
                "Chummer has attached this report to your support case and will send a follow-up after review.",
            });

    private static string BuildAuditedDecisionContent(
        SupportCaseProjection supportCase,
        string decisionOutcome,
        string implementationPosture,
        string reason,
        string etaText,
        string awardLabel)
        => string.Join(
            "\n",
            new[]
            {
                $"Your request was reviewed for case {supportCase.CaseId}.",
                $"Decision: {(decisionOutcome == "approved" ? "approved" : "denied")}",
                $"Implementation posture: {HumanizeImplementationPosture(implementationPosture)}",
                $"Reason: {reason}",
                $"ETA: {etaText}",
                $"Award: {awardLabel}",
                "",
                decisionOutcome == "approved"
                    ? "This is now on the tracked implementation path."
                    : "This will not move forward on the active implementation path right now.",
            });

    private static string BuildFixAvailableContent(
        SupportCaseProjection supportCase,
        SupportCaseNotificationRequest request,
        string downloadUrl,
        string? installRailUrl)
        => string.Join(
            "\n",
            new[]
            {
                $"Your feedback is incorporated in the current release for case {supportCase.CaseId}.",
                request.Note.Trim(),
                "",
                HasInstallRailContext(supportCase)
                    ? "Open the affected claimed desktop install first and tell Chummer if the fix holds there."
                    : "Please test it on the affected flow and tell Chummer if the fix holds.",
                $"Download: {downloadUrl}",
                !string.IsNullOrWhiteSpace(installRailUrl)
                    ? $"Browser fallback for relink or recovery: {installRailUrl}"
                    : string.Empty,
                BuildAffectedInstallLine(supportCase),
                string.IsNullOrWhiteSpace(supportCase.FixedVersion)
                    ? string.Empty
                    : $"Target build: {BuildReleaseLabel(supportCase.FixedChannel, supportCase.FixedVersion)}",
            }.Where(static line => !string.IsNullOrWhiteSpace(line)));

    private static string BuildAffectedInstallLine(SupportCaseProjection supportCase)
    {
        if (!HasInstallRailContext(supportCase))
        {
            return string.Empty;
        }

        string?[] parts =
        [
            supportCase.InstallationId,
            supportCase.ApplicationVersion,
            supportCase.ReleaseChannel,
            supportCase.HeadId,
            supportCase.Platform,
            supportCase.Arch
        ];
        string descriptor = string.Join(" · ", parts.Where(static item => !string.IsNullOrWhiteSpace(item)));
        return string.IsNullOrWhiteSpace(descriptor)
            ? string.Empty
            : $"Affected install: {descriptor}";
    }

    private static bool HasInstallRailContext(SupportCaseProjection supportCase)
        => string.Equals(NormalizeOptional(supportCase.Kind, 64), SupportCaseKinds.InstallHelp, StringComparison.OrdinalIgnoreCase)
           || !string.IsNullOrWhiteSpace(supportCase.InstallationId)
           || !string.IsNullOrWhiteSpace(supportCase.ApplicationVersion)
           || !string.IsNullOrWhiteSpace(supportCase.ReleaseChannel)
           || !string.IsNullOrWhiteSpace(supportCase.HeadId)
           || !string.IsNullOrWhiteSpace(supportCase.Platform)
           || !string.IsNullOrWhiteSpace(supportCase.Arch);

    private static string BuildReleaseLabel(string? channel, string? version)
    {
        string normalizedChannel = NormalizeOptional(channel, 64) ?? "current";
        string normalizedVersion = NormalizeOptional(version, 64) ?? "build";
        return $"{normalizedChannel} {normalizedVersion}";
    }

    private static void AddMetadataIfValue(Dictionary<string, object> metadata, string key, string? value)
    {
        if (!string.IsNullOrWhiteSpace(value))
        {
            metadata[key] = value;
        }
    }

    private static string HumanizeImplementationPosture(string posture)
        => posture switch
        {
            "will_implement" => "will be implemented",
            "not_implemented" => "will not be implemented",
            _ => posture.Replace('_', ' ')
        };

    private static (string awardKey, string awardLabel) ResolveAward(string decisionOutcome, string implementationPosture)
        => decisionOutcome == "approved" || implementationPosture == "will_implement"
            ? ("accepted", "Clad Feedbacker")
            : ("denied", "Denied");

    private static string NormalizeDecisionOutcome(string? requested, string targetStatus)
    {
        string? normalized = NormalizeOptional(requested, 32)?.ToLowerInvariant();
        if (normalized is "approved" or "denied")
        {
            return normalized;
        }

        return targetStatus switch
        {
            SupportCaseStatuses.Accepted => "approved",
            SupportCaseStatuses.Deferred => "denied",
            SupportCaseStatuses.Rejected => "denied",
            _ => "approved"
        };
    }

    private static string NormalizeImplementationPosture(string? requested, string targetStatus)
    {
        string? normalized = NormalizeOptional(requested, 32)?.ToLowerInvariant();
        if (normalized is "will_implement" or "not_implemented")
        {
            return normalized;
        }

        return targetStatus switch
        {
            SupportCaseStatuses.Accepted => "will_implement",
            SupportCaseStatuses.Deferred => "not_implemented",
            SupportCaseStatuses.Rejected => "not_implemented",
            _ => "will_implement"
        };
    }

    private static string DefaultDecisionReason(string targetStatus)
        => targetStatus switch
        {
            SupportCaseStatuses.Accepted => "The report reproduced clearly enough to enter the tracked fix path.",
            SupportCaseStatuses.Deferred => "The report is valid but is not moving on the active implementation lane right now.",
            SupportCaseStatuses.Rejected => "The report did not clear the current acceptance bar with the evidence available.",
            _ => "The current support decision did not provide a more specific reason."
        };

    private static string DefaultEtaText(string targetStatus)
        => targetStatus switch
        {
            SupportCaseStatuses.Accepted => "ETA pending while the implementation lane is scheduled.",
            SupportCaseStatuses.Deferred => "No implementation ETA is committed on this lane.",
            SupportCaseStatuses.Rejected => "No implementation ETA applies to this closed lane.",
            _ => "ETA pending."
        };

    private static SupportProgressEmailDispatchResult BuildSkipped(
        string stageId,
        string recipient,
        string fromEmail,
        string subject,
        string? awardKey,
        string? awardLabel,
        string? decisionOutcome,
        string? implementationPosture,
        string? reason,
        string? etaText,
        string? downloadUrl,
        string? installRailUrl,
        string error,
        DateTimeOffset occurredAtUtc)
        => new(
            StageId: stageId,
            State: "skipped",
            Recipient: recipient,
            FromEmail: fromEmail,
            Subject: subject,
            Provider: EmailitProvider,
            OccurredAtUtc: occurredAtUtc,
            DeliveryId: null,
            AwardKey: awardKey,
            AwardLabel: awardLabel,
            DecisionOutcome: decisionOutcome,
            ImplementationPosture: implementationPosture,
            Reason: reason,
            EtaText: etaText,
            DownloadUrl: downloadUrl,
            InstallRailUrl: installRailUrl,
            Error: error);

    private static SupportProgressEmailDispatchResult BuildFailed(
        string stageId,
        string recipient,
        string fromEmail,
        string subject,
        string? awardKey,
        string? awardLabel,
        string? decisionOutcome,
        string? implementationPosture,
        string? reason,
        string? etaText,
        string? downloadUrl,
        string? installRailUrl,
        string error,
        DateTimeOffset occurredAtUtc,
        string? deliveryId = null)
        => new(
            StageId: stageId,
            State: "failed",
            Recipient: recipient,
            FromEmail: fromEmail,
            Subject: subject,
            Provider: EmailitProvider,
            OccurredAtUtc: occurredAtUtc,
            DeliveryId: deliveryId,
            AwardKey: awardKey,
            AwardLabel: awardLabel,
            DecisionOutcome: decisionOutcome,
            ImplementationPosture: implementationPosture,
            Reason: reason,
            EtaText: etaText,
            DownloadUrl: downloadUrl,
            InstallRailUrl: installRailUrl,
            Error: Truncate(error, 600));

    private string ResolveEaBaseUrl()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BASE_URL"] ?? DefaultEaBaseUrl).Trim().TrimEnd('/');

    private string ResolveEaApiToken()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_API_TOKEN"] ?? string.Empty).Trim();

    private string ResolveEmailitBaseUrl()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_BASE_URL"] ?? DefaultEmailitBaseUrl).Trim().TrimEnd('/');

    private string ResolvePublicBaseUrl()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_PUBLIC_BASE_URL"]
            ?? _configuration["IDENTITY_PUBLIC_BASE_URL"]
            ?? DefaultPublicBaseUrl).Trim().TrimEnd('/');

    private string ResolveFromEmail()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_FROM_EMAIL"] ?? DefaultFromEmail).Trim();

    private string ResolveFromName()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_FROM_NAME"] ?? DefaultFromName).Trim();

    private string ResolveReplyTo()
        => (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_REPLY_TO"] ?? DefaultReplyTo).Trim();

    private bool IsEnabled()
        => !string.Equals(
            (_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_ENABLED"] ?? "true").Trim(),
            "false",
            StringComparison.OrdinalIgnoreCase);

    private static string BuildIdempotencyKey(SupportCaseProjection supportCase, string stageId)
    {
        long updatedTicks = supportCase.UpdatedAtUtc.UtcDateTime.Ticks;
        return $"{supportCase.CaseId}:{stageId}:{updatedTicks}";
    }

    private static string? NormalizeOptional(string? value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        return normalized.Length <= maxLength ? normalized : normalized[..maxLength];
    }

    private static string Truncate(string value, int maxLength)
    {
        if (string.IsNullOrEmpty(value))
        {
            return string.Empty;
        }

        return value.Length <= maxLength ? value : value[..maxLength];
    }

    private static string EscapeHtml(string value)
    {
        StringBuilder builder = new(value.Length);
        foreach (char character in value)
        {
            builder.Append(character switch
            {
                '<' => "&lt;",
                '>' => "&gt;",
                '&' => "&amp;",
                '"' => "&quot;",
                '\'' => "&#39;",
                _ => character
            });
        }

        return builder.ToString();
    }
}
