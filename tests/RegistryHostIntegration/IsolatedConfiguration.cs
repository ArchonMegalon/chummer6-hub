static class IsolatedConfiguration
{
    public static Dictionary<string, string?> Create(string root)
    {
        var configuration = new Dictionary<string, string?>
        {
            ["CHUMMER_PUBLIC_CANONICAL_ORIGIN"] = "http://localhost",
            ["CHUMMER_PUBLIC_ALLOWED_HOSTS"] = "localhost",
            ["AllowedHosts"] = "localhost",
            ["CHUMMER_ENABLE_HTTPS_REDIRECTION"] = "false",
            ["CHUMMER_PUBLIC_ROUTE_WARMUP_ENABLED"] = "false",
            ["CHUMMER_API_READ_RATE_LIMIT_PER_MINUTE"] = "1000",
            ["CHUMMER_API_WRITE_RATE_LIMIT_PER_MINUTE"] = "1000",
            ["CHUMMER_REGISTRY_CONTROL_API_KEY"] = HubFactory.ControlKey,
            ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test",
            // A nonzero cache proves revoked sessions do not reuse cached authority.
            ["CHUMMER_IDENTITY_SUBJECT_CACHE_SECONDS"] = "300",
            ["CHUMMER_ACCOUNT_ERASURE_RECEIPT_HMAC_KEY"] = new string('x', 64),
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = "local",
            ["CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED"] = "false"
        };
        string[] fileKeys =
        [
            "CHUMMER_REGISTRY_ARTIFACT_STORE_PATH", "CHUMMER_COMMUNITY_STORE_PATH",
            "CHUMMER_SUPPORT_STORE_PATH", "CHUMMER_ACCOUNT_ERASURE_JOURNAL_PATH",
            "CHUMMER_INSTALL_LINKING_STORE_PATH", "CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH",
            "CHUMMER_KARMA_FORGE_STORE_PATH", "CHUMMER_PUBLIC_CONCIERGE_STORE_PATH",
            "CHUMMER_PUBLIC_PARTICIPATE_SNAPSHOT_STORE_PATH", "CHUMMER_PRODUCTLIFT_OPERATIONS_STORE_PATH",
            "CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH", "CHUMMER_PAYFUNNELS_BILLING_STORE_PATH",
            "CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH", "CHUMMER_HORIZON_ARTIFACT_USAGE_STORE_PATH",
            "CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH", "CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORE_PATH",
            "CHUMMER_GM_SESSION_VENUE_STORE_PATH", "CHUMMER_GM_SESSION_VIDEO_FOUNDRY_STORE_PATH",
            "CHUMMER_PROMPT_FOUNDRY_STORE_PATH", "CHUMMER_SUBSCRIBR_WEBHOOK_STORE_PATH"
        ];
        foreach (string key in fileKeys) configuration[key] = Path.Combine(root, key + ".json");
        string[] directoryKeys =
        [
            "CHUMMER_RUNTIME_STATE_ROOT", "CHUMMER_DATA_PROTECTION_KEYS_PATH",
            "CHUMMER_PUBLIC_CANON_ROOT", "CHUMMER_DOWNLOADS_SOURCE_ROOT",
            "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT", "CHUMMER_SUPPORT_ATTACHMENT_ROOT",
            "CHUMMER_ORIGIN_DOSSIER_FIRST_PARTY_ROOT", "CHUMMER_SUBSCRIBR_WEBHOOK_RECEIPT_ROOT"
        ];
        foreach (string key in directoryKeys)
        {
            configuration[key] = Path.Combine(root, key);
            Directory.CreateDirectory(configuration[key]!);
        }
        return configuration;
    }
}
