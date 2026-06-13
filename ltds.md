## EA

### default

- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_DEFAULT_EMAIL`
- env_password_key: `CHUMMER_EA_DEFAULT_PASSWORD`
- env_password_alt_key: `CHUMMER_EA_DEFAULT_PASSWORD_ALT`
- applies_to: `1min.AI`, `AI Magicx`, `Prompt Architects`, `ChatPlayground AI`, `BrowserAct`, `Browserly`, `ApproveThis`, `Documentation.AI`, `Icanpreneur`, `MetaSurvey`, `NextStep`, `Nonverbia`, `Teable`, `ApiX-Drive`, `FacePop`, `Deftform`, `Lunacal`, `Paperguide`, `Signitic`, `Emailit`, `Vizologi`, `MarkupGo`, `Soundmadeseen`, `Taja`, `vidBoard`, `PeekShot`, `Crezlo Tours`, `Mootion`, `First Book ai`, `AvoMap`, `Unmixr AI`, `Internxt Cloud Storage`, `Invoiless`, `FastestVPN PRO`, `OneAir`, `Headway`, `ClickRank`, `Katteb`, `ProductLift`, `hedy.ai`, `SendFox`, `Flonnect`, `CutMe Short`, `Backona AI`, `Visby`, `Dadan`, `Rybbit`, `NeuronWriter`

### blipai.app

- tier: `4`
- credential_source: local `.env`
- env_email_key: `CHUMMER_EA_BLIPAI_APP_EMAIL`
- env_password_key: `CHUMMER_EA_BLIPAI_APP_PASSWORD`
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
- required_boundary: `governed memorial video rendering only; Manfred likeness clips require avatar_consent`
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
- status: `bounded_public_analytics_lane`
- required_boundary: `event taxonomy and privacy review must stay discoverable before expanding beyond public-shell telemetry`
- mirrors_default: `false`

### neuronwriter

- tier: `candidate`
- credential_source: local `.env`
- status: `inventory_only`
- required_boundary: `SEO workflow proof required before any public copy or roadmap claim uses NeuronWriter output`
- mirrors_default: `false`
