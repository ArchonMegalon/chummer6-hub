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
        Assert.Contains("tab-combat", script, StringComparison.Ordinal);
        Assert.Contains("tab-info", script, StringComparison.Ordinal);
        Assert.Contains("tab-lifestyle", script, StringComparison.Ordinal);
        Assert.Contains("tab-contacts", script, StringComparison.Ordinal);
        Assert.Contains("tab-notes", script, StringComparison.Ordinal);
        Assert.Contains("tab-calendar", script, StringComparison.Ordinal);
        Assert.Contains("summary", script, StringComparison.Ordinal);
        Assert.Contains("metadata", script, StringComparison.Ordinal);
        Assert.Contains("profile", script, StringComparison.Ordinal);
        Assert.Contains("cyberwares", script, StringComparison.Ordinal);
        Assert.Contains("armors", script, StringComparison.Ordinal);
        Assert.Contains("armormods", script, StringComparison.Ordinal);
        Assert.Contains("armorlocations", script, StringComparison.Ordinal);
        Assert.Contains("arts", script, StringComparison.Ordinal);
        Assert.Contains("attributedetails", script, StringComparison.Ordinal);
        Assert.Contains("weapons", script, StringComparison.Ordinal);
        Assert.Contains("weaponaccessories", script, StringComparison.Ordinal);
        Assert.Contains("weaponlocations", script, StringComparison.Ordinal);
        Assert.Contains("vehiclemods", script, StringComparison.Ordinal);
        Assert.Contains("vehiclelocations", script, StringComparison.Ordinal);
        Assert.Contains("drugs", script, StringComparison.Ordinal);
        Assert.Contains("lifestyles", script, StringComparison.Ordinal);
        Assert.Contains("foci", script, StringComparison.Ordinal);
        Assert.Contains("inventory", script, StringComparison.Ordinal);
        Assert.Contains("gearlocations", script, StringComparison.Ordinal);
        Assert.Contains("customdatadirectorynames", script, StringComparison.Ordinal);
        Assert.Contains("limitmodifiers", script, StringComparison.Ordinal);
        Assert.Contains("movement", script, StringComparison.Ordinal);
        Assert.Contains("martialarts", script, StringComparison.Ordinal);
        Assert.Contains("mentorspirits", script, StringComparison.Ordinal);
        Assert.Contains("metamagics", script, StringComparison.Ordinal);
        Assert.Contains("initiationgrades", script, StringComparison.Ordinal);
        Assert.Contains("powers", script, StringComparison.Ordinal);
        Assert.Contains("critterpowers", script, StringComparison.Ordinal);
        Assert.Contains("aiprograms", script, StringComparison.Ordinal);
        Assert.Contains("spirits", script, StringComparison.Ordinal);
        Assert.Contains("complexforms", script, StringComparison.Ordinal);
        Assert.Contains("vehicles", script, StringComparison.Ordinal);
        Assert.Contains("expenses", script, StringComparison.Ordinal);
        Assert.Contains("sources", script, StringComparison.Ordinal);
        Assert.Contains("rules", script, StringComparison.Ordinal);
        Assert.Contains("validate", script, StringComparison.Ordinal);
        Assert.Contains("combat_add_armor", script, StringComparison.Ordinal);
        Assert.Contains("combat_add_weapon", script, StringComparison.Ordinal);
        Assert.Contains("combat_damage_track", script, StringComparison.Ordinal);
        Assert.Contains("combat_reload", script, StringComparison.Ordinal);
        Assert.Contains("contact_add", script, StringComparison.Ordinal);
        Assert.Contains("contact_connection", script, StringComparison.Ordinal);
        Assert.Contains("contact_remove", script, StringComparison.Ordinal);
        Assert.Contains("create_entry", script, StringComparison.Ordinal);
        Assert.Contains("edit_entry", script, StringComparison.Ordinal);
        Assert.Contains("delete_entry", script, StringComparison.Ordinal);
        Assert.Contains("gear_mount", script, StringComparison.Ordinal);
        Assert.Contains("gear_delete", script, StringComparison.Ordinal);
        Assert.Contains("gear_source", script, StringComparison.Ordinal);
        Assert.Contains("move_down", script, StringComparison.Ordinal);
        Assert.Contains("move_up", script, StringComparison.Ordinal);
        Assert.Contains("open_notes", script, StringComparison.Ordinal);
        Assert.Contains("magic_bind", script, StringComparison.Ordinal);
        Assert.Contains("magic_delete", script, StringComparison.Ordinal);
        Assert.Contains("magic_source", script, StringComparison.Ordinal);
        Assert.Contains("show_source", script, StringComparison.Ordinal);
        Assert.Contains("skill_add", script, StringComparison.Ordinal);
        Assert.Contains("skill_group", script, StringComparison.Ordinal);
        Assert.Contains("skill_remove", script, StringComparison.Ordinal);
        Assert.Contains("skill_specialize", script, StringComparison.Ordinal);
        Assert.Contains("toggle_free_paid", script, StringComparison.Ordinal);
        Assert.Contains("required_milestone2_dialog_factory_controls", script, StringComparison.Ordinal);
        Assert.Contains("adept_power_add", script, StringComparison.Ordinal);
        Assert.Contains("complex_form_add", script, StringComparison.Ordinal);
        Assert.Contains("critter_power_add", script, StringComparison.Ordinal);
        Assert.Contains("cyberware_add", script, StringComparison.Ordinal);
        Assert.Contains("cyberware_delete", script, StringComparison.Ordinal);
        Assert.Contains("cyberware_edit", script, StringComparison.Ordinal);
        Assert.Contains("drug_add", script, StringComparison.Ordinal);
        Assert.Contains("drug_delete", script, StringComparison.Ordinal);
        Assert.Contains("initiation_add", script, StringComparison.Ordinal);
        Assert.Contains("matrix_program_add", script, StringComparison.Ordinal);
        Assert.Contains("quality_add", script, StringComparison.Ordinal);
        Assert.Contains("quality_delete", script, StringComparison.Ordinal);
        Assert.Contains("spell_add", script, StringComparison.Ordinal);
        Assert.Contains("spirit_add", script, StringComparison.Ordinal);
        Assert.Contains("vehicle_add", script, StringComparison.Ordinal);
        Assert.Contains("vehicle_delete", script, StringComparison.Ordinal);
        Assert.Contains("vehicle_edit", script, StringComparison.Ordinal);
        Assert.Contains("vehicle_mod_add", script, StringComparison.Ordinal);
        Assert.Contains("surface_label=\"dialog-factory-only desktop control\"", script, StringComparison.Ordinal);
    }
}
