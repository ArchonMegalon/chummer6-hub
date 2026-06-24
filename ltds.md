## EA

### default

- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_DEFAULT_EMAIL`
- env_password_key: `CHUMMER_EA_DEFAULT_PASSWORD`
- env_password_alt_key: `CHUMMER_EA_DEFAULT_PASSWORD_ALT`
- applies_to: `1min.AI`, `AI Magicx`, `Prompt Architects`, `ChatPlayground AI`, `BrowserAct`, `Browserly`, `ApproveThis`, `Documentation.AI`, `Icanpreneur`, `MetaSurvey`, `NextStep`, `Nonverbia`, `Teable`, `ApiX-Drive`, `FacePop`, `Deftform`, `Lunacal`, `Paperguide`, `Signitic`, `Emailit`, `Vizologi`, `MarkupGo`, `Soundmadeseen`, `Taja`, `vidBoard`, `PeekShot`, `Crezlo Tours`, `Mootion`, `First Book ai`, `MyFirstBook`, `Inkfluence AI`, `ChartBrick`, `AvoMap`, `Unmixr AI`, `Internxt Cloud Storage`, `Invoiless`, `FastestVPN PRO`, `OneAir`, `Headway`, `ClickRank`, `Katteb`, `ProductLift`, `hedy.ai`, `SendFox`, `Flonnect`, `CutMe Short`, `Backona AI`, `Visby`, `Dadan`, `Rybbit`, `NeuronWriter`, `Subscribr`

### blipai.app

- tier: `4`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_BLIPAI_APP_EMAIL`
- env_password_key: `CHUMMER_EA_BLIPAI_APP_PASSWORD`
- mirrors_default: `true`

### chartbrick

- tier: `unlimited`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_CHARTBRICK_EMAIL`
- env_password_key: `CHUMMER_EA_CHARTBRICK_PASSWORD`
- env_explain_embed_url_key: `CHUMMER_ALICE_CHARTBRICK_EXPLAIN_EMBED_URL`
- env_explain_share_url_key: `CHUMMER_ALICE_CHARTBRICK_EXPLAIN_SHARE_URL`
- env_runner_stats_embed_url_key: `CHUMMER_ALICE_CHARTBRICK_RUNNER_STATS_EMBED_URL`
- env_runner_stats_share_url_key: `CHUMMER_ALICE_CHARTBRICK_RUNNER_STATS_SHARE_URL`
- status: `bounded_alice_explanation_and_runner_statistics_lane`
- required_boundary: `ChartBrick may visualize Chummer-owned build explanations and runner statistics only; no rules truth, character authority, account truth, or release truth may originate in ChartBrick`
- mirrors_default: `false`

### icanpreneur

- tier: `3`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_ICANPRENEUR_EMAIL`
- env_password_key: `CHUMMER_EA_ICANPRENEUR_PASSWORD`
- env_base_url_key: `CHUMMER_KARMA_FORGE_ICANPRENEUR_BASE_URL`
- status: `bounded_discovery_interview_lane`
- runtime_ready: `false`
- required_boundary: `adaptive discovery interviews and demand synthesis only; Chummer-owned packets and Product Governor decisions remain canonical; no rules truth, backlog ownership, sourcebook text capture, private campaign truth, release truth, entitlement truth, or publication approval`
- mirrors_default: `true`

### magicfit

- tier: `5`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_MAGICFIT_EMAIL`
- env_password_key: `CHUMMER_EA_MAGICFIT_PASSWORD`
- account_email: `tibor.girschele@gmail.com`
- account_inventory: `3 tracked Tier 5 accounts; one depleted, two available`
- proof_boundary: `each account needs its own render-use receipt before any public asset claims that account produced it`
- mirrors_default: `true`

### magicfit_session

- tier: `5`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL`
- env_password_key: `CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD`
- mirrors_default: `false`
- notes: `GM-session video foundry account for campaign/table-pulse media. Separate from official product media account.`

### inkfluence

- tier: `3`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_INKFLUENCE_EMAIL`
- env_password_key: `CHUMMER_EA_INKFLUENCE_PASSWORD`
- env_email_alt_key: `CHUMMER_EA_INKFLUENCE_EMAIL_ALT`
- env_password_alt_key: `CHUMMER_EA_INKFLUENCE_PASSWORD_ALT`
- env_email_alt2_key: `CHUMMER_EA_INKFLUENCE_EMAIL_ALT2`
- env_password_alt2_key: `CHUMMER_EA_INKFLUENCE_PASSWORD_ALT2`
- env_base_url_key: `CHUMMER_EA_INKFLUENCE_BASE_URL`
- account_inventory: `3 tracked Tier 3 accounts; default plus 2 alternates available`
- status: `supporter_only_deluxe_origin_book_finishing_lane`
- runtime_ready: `false`
- required_boundary: `Inkfluence may package approved Chummer canon into deluxe memoir, cover, export, and audiobook variants only; it must never own runner history, rules truth, campaign canon, entitlement truth, or publication approval`
- mirrors_default: `false`

### prompt_architects

- tier: `4`
- credential_source: local `.env`
- env_api_key: `PROMPTING_SYSTEMS_API_KEY`
- env_account_verified_key: `PROMPT_ARCHITECTS_TIER4_VERIFIED`
- env_api_available_key: `PROMPT_ARCHITECTS_API_AVAILABLE`
- env_mcp_verified_key: `PROMPT_ARCHITECTS_MCP_VERIFIED`
- env_export_available_key: `PROMPT_ARCHITECTS_EXPORT_AVAILABLE`
- env_import_available_key: `PROMPT_ARCHITECTS_IMPORT_AVAILABLE`
- env_data_retention_reviewed_key: `PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED`
- env_team_permissions_reviewed_key: `PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED`
- mirrors_default: `false`

### payfunnels

- tier: `3`
- credential_source: local `.env`
- env_webhook_secret_key: `PAYFUNNELS_WEBHOOK_SECRET`
- env_checkout_url_key: `PAYFUNNELS_TEST_CHECKOUT_URL`
- env_billing_store_path_key: `CHUMMER_PAYFUNNELS_BILLING_STORE_PATH`
- mirrors_default: `false`

### unmixr

- tier: `4`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_UNMIXR_EMAIL`
- env_password_key: `CHUMMER_EA_UNMIXR_PASSWORD`
- env_username_key: `UNMIXR_USERNAME`
- env_login_password_key: `UNMIXR_PASSWORD`
- env_api_key: `UNMIXR_API_KEY`
- env_voice_id_key: `UNMIXR_VOICE_ID`
- mirrors_default: `true`
- runtime_boundary: `passing EA-local runtime proof exists for private API key, selected voice id, Piper fallback, and voice roundtrip validation; secrets stay outside git`

### joggai

- tier: `4`
- credential_source: local `.env`
- status: `tracked_in_discovery`
- runtime_ready: `false`
- required_boundary: `candidate avatar and character video rendering only; Chummer Origin Dossier or claim-copy scenes require explicit likeness/data consent, provider proof, privacy review, and human approval before use`
- mirrors_default: `false`

### dadan

- tier: `candidate`
- credential_source: local `.env`
- status: `inventory_only`
- required_boundary: `video report workflow must be provider-verified before use in Chummer public media or support copy`
- mirrors_default: `false`

### rybbit

- tier: `analytics`
- credential_source: local `.env`
- env_script_url_key: `RYBBIT_CHUMMER_RUN_SCRIPT_URL`
- env_script_origin_key: `RYBBIT_CHUMMER_RUN_SCRIPT_ORIGIN`
- env_same_host_proxy_key: `RYBBIT_CHUMMER_RUN_ALLOW_SAME_HOST_PROXY`
- env_desktop_site_id_key: `RYBBIT_CHUMMER_DESKTOP_SITE_ID`
- env_desktop_api_key: `RYBBIT_CHUMMER_DESKTOP_API_KEY`
- env_desktop_api_origin_key: `RYBBIT_CHUMMER_DESKTOP_API_ORIGIN`
- status: `bounded_public_and_desktop_analytics_lane`
- required_boundary: `event taxonomy and privacy review must stay discoverable; CTA instrumentation and desktop shell events stay first-party, opt-in, and bounded to non-character metadata`
- mirrors_default: `false`

### clickrank

- tier: `visibility`
- credential_source: local `.env`
- env_site_id_key: `CLICKRANK_AI_CHUMMER_RUN_SITE_ID`
- status: `bounded_public_visibility_lane`
- required_boundary: `recommendations only; Chummer-owned source patches stay canonical and reviewed before publication`
- mirrors_default: `false`

### neuronwriter

- tier: `candidate`
- credential_source: local `.env`
- status: `bounded_source_packet_seo_lane`
- required_boundary: `source-packet SEO workflow only; Chummer-owned copy remains canonical and no release, support, roadmap, or rules claim may originate in NeuronWriter`
- mirrors_default: `false`

### subscribr

- tier: `License Tier 7 / Scale 3`
- workspace_tier: `4`
- credential_source: local `.env`
- env_api_token_key: `SUBSCRIBR_API_TOKEN`
- env_webhook_secret_key: `SUBSCRIBR_WEBHOOK_SECRET`
- env_team_id_key: `SUBSCRIBR_TEAM_ID`
- env_integration_channel_id_key: `SUBSCRIBR_INTEGRATION_CHANNEL_ID`
- status: `tracked_video_script_preproduction_lane`
- runtime_ready: `false`
- required_boundary: `governed video script pre-production only; Chummer-owned source packets remain canonical and Subscribr may not own rules truth, release truth, private campaign data, entitlement truth, or publication approval`
- mirrors_default: `false`

### rafter

- tier: `qa`
- credential_source: provider account
- status: `auxiliary_release_qa_lane`
- required_boundary: `security, accessibility, performance, SEO, and live-site evidence only; no product truth or deploy authority`
- mirrors_default: `false`

### pixefy

- tier: `qa`
- credential_source: provider account
- status: `auxiliary_visual_qa_lane`
- required_boundary: `responsive screenshot and visual QA only; no product truth, private data inspection, or media-authority role`
- mirrors_default: `false`
