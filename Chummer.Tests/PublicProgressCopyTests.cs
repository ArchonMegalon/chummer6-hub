using Chummer.Run.Api.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicProgressCopyTests
{
    [Fact]
    public void ProgressControllerUsesCurrentReleaseLanguageForCustomerFacingReferences()
    {
        string controller = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs"));

        Assert.Contains("Customer-facing current state lives on Current release.", controller, StringComparison.Ordinal);
        Assert.Contains("Current customer state lives on <a href=\"/now\">Current release</a>.", controller, StringComparison.Ordinal);
        Assert.Contains(">Open current release<", controller, StringComparison.Ordinal);

        Assert.DoesNotContain("What works today", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Open What works today", controller, StringComparison.Ordinal);
    }
}

public sealed class PublicProgressServiceTests
{
    [Fact]
    public void StrictConfiguredRootLoadsStagedProgressArtifact()
    {
        string root = CreateTestRoot();
        try
        {
            string productRoot = Path.Combine(root, ".codex-design", "product");
            Directory.CreateDirectory(productRoot);
            File.WriteAllText(
                Path.Combine(productRoot, "PROGRESS_REPORT.generated.json"),
                "{\"source\":\"candidate-bound\"}");
            PublicProgressService service = CreateService(CreateStrictConfiguration(root));

            string report = service.LoadReportJson();

            Assert.Contains("candidate-bound", report, StringComparison.Ordinal);
        }
        finally
        {
            DeleteTestRoot(root);
        }
    }

    [Fact]
    public void StrictConfiguredRootDoesNotFallBackForMissingProgressArtifact()
    {
        string root = CreateTestRoot();
        try
        {
            PublicProgressService service = CreateService(CreateStrictConfiguration(root));

            Assert.Throws<DirectoryNotFoundException>(() => service.LoadReportJson());
        }
        finally
        {
            DeleteTestRoot(root);
        }
    }

    [Fact]
    public void StrictConfiguredRootRejectsRelativeProgressRoot()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = "relative-progress-root",
                ["CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"
            })
            .Build();
        PublicProgressService service = CreateService(configuration);

        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() => service.LoadReportJson());

        Assert.Contains("absolute path", exception.Message, StringComparison.Ordinal);
    }

    private static PublicProgressService CreateService(IConfiguration configuration)
    {
        WeeklyProductPulseArtifactService weeklyPulse = new(
            configuration,
            NullLogger<WeeklyProductPulseArtifactService>.Instance);
        return new PublicProgressService(
            configuration,
            weeklyPulse,
            NullLogger<PublicProgressService>.Instance);
    }

    private static IConfiguration CreateStrictConfiguration(string root)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PUBLIC_CANON_ROOT"] = root,
                ["CHUMMER_PUBLIC_STRICT_CONFIGURED_ROOT"] = "true"
            })
            .Build();

    private static string CreateTestRoot()
    {
        string root = Path.Combine(Path.GetTempPath(), "public-progress-service-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        return root;
    }

    private static void DeleteTestRoot(string root)
    {
        if (Directory.Exists(root))
        {
            Directory.Delete(root, recursive: true);
        }
    }
}
