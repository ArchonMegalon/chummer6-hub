using System.Text;
using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class ArtifactDeliveryPolicyPayloadSidecarTests
{
    [Fact]
    public void GenerationBoundPayloadRoleSidecarIsValid()
    {
        const string installer = "chummer-avalonia-win-x64-installer.exe";
        const string payload = "chummer-avalonia-win-x64-payload.zip";
        const string digest = "ce5bfb82aeee8e1fafb917d06a720829fc14199731bb60df0f009b7a32db67cc";
        const string version = "run-20260731-095000";
        const string url = "/downloads/g/gen-20260731T082441Z-c6e5c31ce81e4ef4/install/avalonia-win-x64-installer/payload";
        byte[] sidecar = Encoding.UTF8.GetBytes(
            "{\"contractName\":\"chummer6-ui.windows_bootstrap_payload\","
            + $"\"fileName\":\"{payload}\","
            + $"\"downloadUrl\":\"{url}\","
            + $"\"sha256\":\"{digest}\","
            + "\"sizeBytes\":51115389,"
            + $"\"installerFileName\":\"{installer}\","
            + $"\"releaseVersion\":\"{version}\","
            + "\"payloadAcquisitionMode\":\"download\"}");

        bool valid = PayloadSidecarContractValidator.TryValidate(
            sidecar,
            installer,
            payload,
            url,
            digest,
            51115389,
            version,
            "download",
            allowMutableIncomingUrl: false,
            out string? failure);

        Assert.True(valid, failure);
    }
}
