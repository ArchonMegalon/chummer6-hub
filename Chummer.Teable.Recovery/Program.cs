using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Chummer.Storage.Teable;

// No token/secret values on the command line or in output. This is an operator
// file-custody tool, not a Hub endpoint or a deployment controller.
if (args.Length != 2 || args[0] is not ("capture" or "inspect" or "restore"))
{
    Console.Error.WriteLine("Usage: Chummer.Teable.Recovery <capture|inspect|restore> <absolute-private-options.json>");
    return 2;
}

try
{
    if (!Path.IsPathFullyQualified(args[1])) throw new InvalidDataException();
    LinuxSecureFile.ValidateExistingPrivateFile(args[1]);
    byte[] bytes = LinuxSecureFile.ReadOwnerOnlyRegularFile(args[1], 32 * 1024, repairOwnerMode: false);
    Options options;
    try
    {
        using (JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 8 }))
            TeableRecoveryBundleStore.RejectDuplicateProperties(document.RootElement);
        options = JsonSerializer.Deserialize<Options>(bytes, new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = false,
            UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
            MaxDepth = 8
        }) ?? throw new InvalidDataException();
    }
    finally { CryptographicOperations.ZeroMemory(bytes); }
    using var store = TeableRevisionStore.OpenFromPrivateTokenFile(options.Origin, options.TableId, options.TokenFile);
    var bundles = new TeableRecoveryBundleStore(store);
    using var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(5));
    TeableRecoveryBundleStore.Receipt result = args[0] switch
    {
        "capture" => await bundles.CaptureAsync(options.Deployment,
            options.SourceDirectory ?? throw new InvalidDataException(),
            options.Files ?? throw new InvalidDataException(), deadline.Token),
        "inspect" => await bundles.InspectAsync(options.Deployment, deadline.Token),
        "restore" when options.Expected?.Deployment == options.Deployment => await bundles.RestoreAsync(options.Expected,
            options.DestinationParent ?? throw new InvalidDataException(),
            options.DirectoryName ?? throw new InvalidDataException(), deadline.Token),
        _ => throw new InvalidDataException()
    };
    Console.WriteLine(JsonSerializer.Serialize(new { status = "ok", operation = args[0], receipt = result, cutoverPerformed = false },
        new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    return 0;
}
catch (Exception error)
{
    // Do not expose remote response text, JSON paths, secrets or framework
    // exceptions. On an uncertain capture, inspect: never replay automatically.
    string code = error is TeableRevisionConflictException ? "remote_revision_changed" : "recovery_not_completed";
    Console.Error.WriteLine(JsonSerializer.Serialize(new { status = "failed", code, cutoverPerformed = false }));
    return 1;
}

internal sealed record Options(Uri Origin, string TableId, string TokenFile, string Deployment,
    string? SourceDirectory = null, string[]? Files = null, string? DestinationParent = null,
    string? DirectoryName = null, TeableRecoveryBundleStore.Receipt? Expected = null);
