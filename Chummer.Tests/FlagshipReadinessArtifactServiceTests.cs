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
        string fallbackRoot = Path.Combine(tempRoot, "fleet", ".codex-studio", "published");
        Directory.CreateDirectory(fallbackRoot);

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
            File.WriteAllText(
                Path.Combine(fallbackRoot, "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-06-27T19:45:08Z",
                  "status": "pass",
                  "flagship_readiness_audit": {
                    "reason": "current fleet readiness artifact",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": []
                  }
                }
                """);

            Directory.SetCurrentDirectory(tempRoot);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FALLBACK_FILE"] = Path.Combine(fallbackRoot, "FLAGSHIP_PRODUCT_READINESS.generated.json")
                })
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

    [Fact]
    public void LoadSnapshotUsesConfiguredPrimaryReadinessFileWhenPresent()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "flagship-readiness-artifact-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);

        try
        {
            string primaryPath = Path.Combine(tempRoot, "configured-primary.json");
            string fallbackPath = Path.Combine(tempRoot, "fallback.json");
            File.WriteAllText(
                primaryPath,
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-06-20T08:00:00Z",
                  "status": "fail",
                  "flagship_readiness_audit": {
                    "reason": "configured primary wins",
                    "missing_coverage_keys": ["desktop_client"],
                    "scoped_missing_coverage_keys": ["desktop_client"]
                  }
                }
                """);
            File.WriteAllText(
                fallbackPath,
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-06-27T19:45:08Z",
                  "status": "pass",
                  "flagship_readiness_audit": {
                    "reason": "fallback should not override configured primary",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": []
                  }
                }
                """);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FILE"] = primaryPath,
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FALLBACK_FILE"] = fallbackPath
                })
                .Build();

            var service = new FlagshipReadinessArtifactService(configuration);
            FlagshipReadinessSnapshot? snapshot = service.LoadSnapshot();

            Assert.NotNull(snapshot);
            Assert.Equal("fail", snapshot!.Status);
            Assert.True(snapshot.MissingDesktopClientCoverage);
            Assert.Equal("configured primary wins", snapshot.Reason);
        }
        finally
        {
            try
            {
                Directory.Delete(tempRoot, recursive: true);
            }
            catch
            {
            }
        }
    }

    [Fact]
    public void LoadSnapshotDoesNotLetOlderPassingFallbackOverrideNewerFailingLocalArtifact()
    {
        string originalCurrentDirectory = Directory.GetCurrentDirectory();
        string tempRoot = Path.Combine(Path.GetTempPath(), "flagship-readiness-artifact-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(tempRoot, ".codex-studio", "published"));
        string fallbackRoot = Path.Combine(tempRoot, "fleet", ".codex-studio", "published");
        Directory.CreateDirectory(fallbackRoot);

        try
        {
            File.WriteAllText(
                Path.Combine(tempRoot, ".codex-studio", "published", "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-07-02T15:44:23Z",
                  "status": "fail",
                  "flagship_readiness_audit": {
                    "reason": "newer local readiness says desktop coverage is missing",
                    "missing_coverage_keys": ["desktop_client"],
                    "scoped_missing_coverage_keys": ["desktop_client"]
                  }
                }
                """);
            File.WriteAllText(
                Path.Combine(fallbackRoot, "FLAGSHIP_PRODUCT_READINESS.generated.json"),
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-07-02T04:53:26Z",
                  "status": "pass",
                  "flagship_readiness_audit": {
                    "reason": "older fleet fallback should not win",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": []
                  }
                }
                """);

            Directory.SetCurrentDirectory(tempRoot);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FALLBACK_FILE"] = Path.Combine(fallbackRoot, "FLAGSHIP_PRODUCT_READINESS.generated.json")
                })
                .Build();

            var service = new FlagshipReadinessArtifactService(configuration);
            FlagshipReadinessSnapshot? snapshot = service.LoadSnapshot();

            Assert.NotNull(snapshot);
            Assert.Equal("fail", snapshot!.Status);
            Assert.True(snapshot.MissingDesktopClientCoverage);
            Assert.Equal("newer local readiness says desktop coverage is missing", snapshot.Reason);
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

    [Fact]
    public void LoadSnapshotFallsBackWhenCurrentDirectoryIsUnavailable()
    {
        string originalCurrentDirectory = Directory.GetCurrentDirectory();
        string tempRoot = Path.Combine(Path.GetTempPath(), "flagship-readiness-artifact-tests", Guid.NewGuid().ToString("N"));
        string deletedCurrentDirectory = Path.Combine(tempRoot, "deleted-cwd");
        Directory.CreateDirectory(deletedCurrentDirectory);

        try
        {
            string fallbackPath = Path.Combine(tempRoot, "fallback.json");
            File.WriteAllText(
                fallbackPath,
                """
                {
                  "contract_name": "fleet.flagship_product_readiness",
                  "generated_at": "2026-07-09T07:50:00Z",
                  "status": "pass",
                  "flagship_readiness_audit": {
                    "reason": "fallback remains readable when cwd is gone",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": []
                  }
                }
                """);

            Directory.SetCurrentDirectory(deletedCurrentDirectory);
            Directory.Delete(deletedCurrentDirectory, recursive: true);

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_FLAGSHIP_READINESS_FALLBACK_FILE"] = fallbackPath
                })
                .Build();

            var service = new FlagshipReadinessArtifactService(configuration);
            FlagshipReadinessSnapshot? snapshot = service.LoadSnapshot();

            Assert.NotNull(snapshot);
            Assert.Equal("pass", snapshot!.Status);
            Assert.Equal("fallback remains readable when cwd is gone", snapshot.Reason);
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
