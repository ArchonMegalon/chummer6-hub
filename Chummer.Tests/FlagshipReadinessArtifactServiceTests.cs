using System;
using System.Collections.Generic;
using System.IO;
using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class FlagshipReadinessArtifactServiceTests
{
    [Fact]
    public void LoadSnapshotPrefersFreshestAvailableArtifact()
    {
        string originalCurrentDirectory = Directory.GetCurrentDirectory();
        string tempRoot = Path.Combine(Path.GetTempPath(), "flagship-readiness-artifact-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(tempRoot, ".codex-studio", "published"));

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, ".codex-studio", "published", "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-05-17T19:40:03Z",
                  "status": "fail",
                  "flagship_readiness_audit": {
                    "reason": "stale local readiness artifact",
                    "missing_coverage_keys": ["desktop_client"],
                    "scoped_missing_coverage_keys": ["desktop_client"]
                  }
                }
                """);

            Directory.SetCurrentDirectory(tempRoot);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>())
                .Build();

            var service = new FlagshipReadinessArtifactService(configuration);
            FlagshipReadinessSnapshot? snapshot = service.LoadSnapshot();

            Assert.NotNull(snapshot);
            Assert.Equal("pass", snapshot!.Status);
            Assert.False(snapshot.MissingDesktopClientCoverage);
        }
        finally
        {
            Directory.SetCurrentDirectory(originalCurrentDirectory);
            try
            {
                Directory.Delete(tempRoot, recursive: true);
            }
            catch
            {
            }
        }
    }
}
