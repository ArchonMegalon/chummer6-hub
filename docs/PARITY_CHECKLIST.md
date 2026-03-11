# UI Parity Checklist

Generated automatically from the parity oracle and current contracts catalogs.

- Regenerate command: `RUNBOOK_MODE=parity-checklist bash scripts/runbook.sh`
- Parity oracle source: `docs/PARITY_ORACLE.json`
- Tab catalog source: `Chummer.Rulesets.Hosting/Presentation/NavigationTabCatalog.cs`
- Action catalog source: `Chummer.Rulesets.Hosting/Presentation/WorkspaceSurfaceActionCatalog.cs`
- Workspace Actions coverage compares parity-oracle action IDs to action `TargetId` values.
- Legacy desktop control parity is enforced by dialog-template compliance tests, not by a shared control catalog.

## Summary

| Surface | Legacy IDs | Covered | Missing In Catalog | Catalog Only |
| --- | ---: | ---: | ---: | ---: |
| Tabs | 17 | 17 | 0 | 1 |
| Workspace Actions | 47 | 47 | 0 | 1 |

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
| `tab-rules` | catalog_only |

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
| `data_exporter` | catalog_only |
