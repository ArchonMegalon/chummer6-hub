using Xunit;

namespace Chummer.Tests;

public sealed class ParityChecklistMilestone2BaselineTests
{
    [Fact]
    public void ParityChecklistGeneratorFailClosesMilestone2BaselineSurfaceFamilies()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "generate-parity-checklist.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("fail_on_missing_milestone2_baseline_ids", script, StringComparison.Ordinal);
        Assert.Contains("required_milestone2_tabs", script, StringComparison.Ordinal);
        Assert.Contains("required_milestone2_actions", script, StringComparison.Ordinal);
        Assert.Contains("required_milestone2_desktop_controls", script, StringComparison.Ordinal);
        Assert.Contains("is missing required milestone-2 baseline", script, StringComparison.Ordinal);
        Assert.Contains("tab-cyberware", script, StringComparison.Ordinal);
        Assert.Contains("tab-armor", script, StringComparison.Ordinal);
        Assert.Contains("tab-adept", script, StringComparison.Ordinal);
        Assert.Contains("tab-lifestyle", script, StringComparison.Ordinal);
        Assert.Contains("tab-contacts", script, StringComparison.Ordinal);
        Assert.Contains("tab-notes", script, StringComparison.Ordinal);
        Assert.Contains("tab-calendar", script, StringComparison.Ordinal);
        Assert.Contains("cyberwares", script, StringComparison.Ordinal);
        Assert.Contains("armors", script, StringComparison.Ordinal);
        Assert.Contains("armormods", script, StringComparison.Ordinal);
        Assert.Contains("weapons", script, StringComparison.Ordinal);
        Assert.Contains("weaponaccessories", script, StringComparison.Ordinal);
        Assert.Contains("vehiclemods", script, StringComparison.Ordinal);
        Assert.Contains("drugs", script, StringComparison.Ordinal);
        Assert.Contains("lifestyles", script, StringComparison.Ordinal);
        Assert.Contains("metamagics", script, StringComparison.Ordinal);
        Assert.Contains("initiationgrades", script, StringComparison.Ordinal);
        Assert.Contains("aiprograms", script, StringComparison.Ordinal);
        Assert.Contains("spirits", script, StringComparison.Ordinal);
        Assert.Contains("complexforms", script, StringComparison.Ordinal);
        Assert.Contains("vehicles", script, StringComparison.Ordinal);
        Assert.Contains("combat_add_armor", script, StringComparison.Ordinal);
        Assert.Contains("combat_add_weapon", script, StringComparison.Ordinal);
        Assert.Contains("contact_add", script, StringComparison.Ordinal);
        Assert.Contains("contact_remove", script, StringComparison.Ordinal);
        Assert.Contains("create_entry", script, StringComparison.Ordinal);
        Assert.Contains("edit_entry", script, StringComparison.Ordinal);
        Assert.Contains("delete_entry", script, StringComparison.Ordinal);
        Assert.Contains("gear_mount", script, StringComparison.Ordinal);
        Assert.Contains("open_notes", script, StringComparison.Ordinal);
        Assert.Contains("magic_bind", script, StringComparison.Ordinal);
    }
}
