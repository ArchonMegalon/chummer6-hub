# UI Parity Checklist

Generated automatically from the parity oracle and current contracts catalogs.

- Regenerate command: `RUNBOOK_MODE=parity-checklist bash scripts/runbook.sh`
- Parity oracle source: `docs/PARITY_ORACLE.json`
- Tab catalog source: `../chummer-core-engine/Chummer.Rulesets.Hosting/Presentation/NavigationTabCatalog.cs`
- Action catalog source: `../chummer-core-engine/Chummer.Rulesets.Hosting/Presentation/WorkspaceSurfaceActionCatalog.cs`
- Desktop dialog source: `../chummer-presentation/Chummer.Presentation/Overview/DesktopDialogFactory.cs`
- Overview command policy source: `../chummer-presentation/Chummer.Presentation/Overview/OverviewCommandPolicy.cs`
- Workspace Actions coverage compares parity-oracle action IDs to action `TargetId` values.
- Catalog-only IDs must be acknowledged explicitly in `docs/PARITY_ORACLE.json`.
- Desktop Controls coverage compares parity-oracle control IDs to dialog control IDs in `DesktopDialogFactory`, excluding import-hint command routes declared in `OverviewCommandPolicy`.
- Dialog-factory-only desktop controls must be acknowledged explicitly in `docs/PARITY_ORACLE.json`.

## Summary

| Surface | Legacy IDs | Covered | Missing In Catalog | Catalog Only |
| --- | ---: | ---: | ---: | ---: |
| Tabs | 17 | 17 | 0 | 5 |
| Workspace Actions | 47 | 47 | 0 | 9 |
| Desktop Controls | 29 | 29 | 0 | 57 |

## Tabs Coverage

| ID | Status |
| --- | --- |
| `tab-adept` | covered |
| `tab-armor` | covered |
| `tab-attributes` | covered |
| `tab-calendar` | covered |
| `tab-combat` | covered |
| `tab-contacts` | covered |
| `tab-cyberware` | covered |
| `tab-gear` | covered |
| `tab-improvements` | covered |
| `tab-info` | covered |
| `tab-lifestyle` | covered |
| `tab-magician` | covered |
| `tab-notes` | covered |
| `tab-qualities` | covered |
| `tab-skills` | covered |
| `tab-technomancer` | covered |
| `tab-vehicles` | covered |
| `tab-create` | catalog_only_acknowledged |
| `tab-karma` | catalog_only_acknowledged |
| `tab-relationships` | catalog_only_acknowledged |
| `tab-rules` | catalog_only_acknowledged |
| `tab-streetgear` | catalog_only_acknowledged |

## Workspace Actions Coverage

| ID | Status |
| --- | --- |
| `aiprograms` | covered |
| `armorlocations` | covered |
| `armormods` | covered |
| `armors` | covered |
| `arts` | covered |
| `attributedetails` | covered |
| `attributes` | covered |
| `awakening` | covered |
| `build` | covered |
| `calendar` | covered |
| `complexforms` | covered |
| `contacts` | covered |
| `critterpowers` | covered |
| `customdatadirectorynames` | covered |
| `cyberwares` | covered |
| `drugs` | covered |
| `expenses` | covered |
| `foci` | covered |
| `gear` | covered |
| `gearlocations` | covered |
| `improvements` | covered |
| `initiationgrades` | covered |
| `inventory` | covered |
| `lifestyles` | covered |
| `limitmodifiers` | covered |
| `martialarts` | covered |
| `mentorspirits` | covered |
| `metadata` | covered |
| `metamagics` | covered |
| `movement` | covered |
| `powers` | covered |
| `profile` | covered |
| `progress` | covered |
| `qualities` | covered |
| `rules` | covered |
| `skills` | covered |
| `sources` | covered |
| `spells` | covered |
| `spirits` | covered |
| `summary` | covered |
| `validate` | covered |
| `vehiclelocations` | covered |
| `vehiclemods` | covered |
| `vehicles` | covered |
| `weaponaccessories` | covered |
| `weaponlocations` | covered |
| `weapons` | covered |
| `build-lab` | catalog_only_acknowledged |
| `conditionmonitor` | catalog_only_acknowledged |
| `data_exporter` | catalog_only_acknowledged |
| `enemies` | catalog_only_acknowledged |
| `karmasummary` | catalog_only_acknowledged |
| `pets` | catalog_only_acknowledged |
| `relationships` | catalog_only_acknowledged |
| `spelldefense` | catalog_only_acknowledged |
| `sprites` | catalog_only_acknowledged |

## Desktop Controls Coverage

| ID | Status |
| --- | --- |
| `combat_add_armor` | covered |
| `combat_add_weapon` | covered |
| `combat_damage_track` | covered |
| `combat_reload` | covered |
| `contact_add` | covered |
| `contact_connection` | covered |
| `contact_edit` | covered |
| `contact_remove` | covered |
| `create_entry` | covered |
| `delete_entry` | covered |
| `edit_entry` | covered |
| `gear_add` | covered |
| `gear_delete` | covered |
| `gear_edit` | covered |
| `gear_mount` | covered |
| `gear_source` | covered |
| `magic_add` | covered |
| `magic_bind` | covered |
| `magic_delete` | covered |
| `magic_source` | covered |
| `move_down` | covered |
| `move_up` | covered |
| `open_notes` | covered |
| `show_source` | covered |
| `skill_add` | covered |
| `skill_group` | covered |
| `skill_remove` | covered |
| `skill_specialize` | covered |
| `toggle_free_paid` | covered |
| `about` | present_in_dialog_factory_acknowledged |
| `adept_power_add` | present_in_dialog_factory_acknowledged |
| `character_roster` | present_in_dialog_factory_acknowledged |
| `character_settings` | present_in_dialog_factory_acknowledged |
| `close_window` | present_in_dialog_factory_acknowledged |
| `complex_form_add` | present_in_dialog_factory_acknowledged |
| `critter_power_add` | present_in_dialog_factory_acknowledged |
| `cyberware_add` | present_in_dialog_factory_acknowledged |
| `cyberware_delete` | present_in_dialog_factory_acknowledged |
| `cyberware_edit` | present_in_dialog_factory_acknowledged |
| `data_exporter` | present_in_dialog_factory_acknowledged |
| `dice_roller` | present_in_dialog_factory_acknowledged |
| `discord` | present_in_dialog_factory_acknowledged |
| `drug_add` | present_in_dialog_factory_acknowledged |
| `drug_delete` | present_in_dialog_factory_acknowledged |
| `dumpshock` | present_in_dialog_factory_acknowledged |
| `export_character` | present_in_dialog_factory_acknowledged |
| `global_settings` | present_in_dialog_factory_acknowledged |
| `hero_lab_importer` | present_in_dialog_factory_acknowledged |
| `identity_license_add` | present_in_dialog_factory_acknowledged |
| `identity_license_delete` | present_in_dialog_factory_acknowledged |
| `identity_license_edit` | present_in_dialog_factory_acknowledged |
| `initiation_add` | present_in_dialog_factory_acknowledged |
| `master_index` | present_in_dialog_factory_acknowledged |
| `matrix_program_add` | present_in_dialog_factory_acknowledged |
| `new_character` | present_in_dialog_factory_acknowledged |
| `new_character_origin` | present_in_dialog_factory_acknowledged |
| `new_window` | present_in_dialog_factory_acknowledged |
| `open_custom_data` | present_in_dialog_factory_acknowledged |
| `open_data_folder` | present_in_dialog_factory_acknowledged |
| `open_errata` | present_in_dialog_factory_acknowledged |
| `open_sourcebooks` | present_in_dialog_factory_acknowledged |
| `print_character` | present_in_dialog_factory_acknowledged |
| `print_multiple` | present_in_dialog_factory_acknowledged |
| `print_setup` | present_in_dialog_factory_acknowledged |
| `quality_add` | present_in_dialog_factory_acknowledged |
| `quality_delete` | present_in_dialog_factory_acknowledged |
| `report_bug` | present_in_dialog_factory_acknowledged |
| `revision_history` | present_in_dialog_factory_acknowledged |
| `runner_benchmark` | present_in_dialog_factory_acknowledged |
| `runner_cohort_privacy` | present_in_dialog_factory_acknowledged |
| `runner_what_if` | present_in_dialog_factory_acknowledged |
| `show_login_video` | present_in_dialog_factory_acknowledged |
| `spell_add` | present_in_dialog_factory_acknowledged |
| `spirit_add` | present_in_dialog_factory_acknowledged |
| `sprite_add` | present_in_dialog_factory_acknowledged |
| `switch_ruleset` | present_in_dialog_factory_acknowledged |
| `translator` | present_in_dialog_factory_acknowledged |
| `update` | present_in_dialog_factory_acknowledged |
| `update_data_packs` | present_in_dialog_factory_acknowledged |
| `validate_data_scope` | present_in_dialog_factory_acknowledged |
| `vehicle_add` | present_in_dialog_factory_acknowledged |
| `vehicle_delete` | present_in_dialog_factory_acknowledged |
| `vehicle_edit` | present_in_dialog_factory_acknowledged |
| `vehicle_mod_add` | present_in_dialog_factory_acknowledged |
| `wiki` | present_in_dialog_factory_acknowledged |
| `xml_editor` | present_in_dialog_factory_acknowledged |
