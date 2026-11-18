using Microsoft.Win32.SafeHandles;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

internal static partial class Program
{
    private const int MaximumBundleBytes = 2 * 1024 * 1024;
    private const int MaximumPasswordBytes = 16 * 1024;
    private const int MaximumCertificatesInBundle = 16;
    private const int MaximumPrivateKeyCertificates = 8;
    private const uint ExpectedOwnerUserId = 1000;
    private const int OpenReadOnly = 0;
    private const int OpenWriteOnly = 1;
    private const int OpenCreate = 0x40;
    private const int OpenExclusive = 0x80;
    private const int OpenCloseOnExec = 0x80000;
    private const int OpenNoFollow = 0x20000;
    private const int OpenDirectory = 0x10000;
    private const int AtRemoveDirectory = 0x200;
    private const uint FileTypeMask = 0xF000;
    private const uint RegularFile = 0x8000;
    private const uint DirectoryFile = 0x4000;
    private const uint OwnerReadOnlyMode = 0x100;
    private const uint OwnerReadWriteMode = 0x180;
    private const uint OwnerDirectoryMode = 0x1C0;

    public static int Main(string[] arguments)
    {
        try
        {
            Arguments options = Arguments.Parse(arguments);
            Receipt receipt = Materialize(options);
            Console.Out.WriteLine(JsonSerializer.Serialize(receipt, JsonOptions));
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine($"data-protection bundle materialization failed: {exception.Message}");
            return 70;
        }
    }

    private static Receipt Materialize(Arguments options)
    {
        if (!OperatingSystem.IsLinux()
            || RuntimeInformation.ProcessArchitecture != Architecture.X64
            || NativeGetEffectiveUserId() != ExpectedOwnerUserId)
        {
            throw new PlatformNotSupportedException(
                "bundle materialization requires the Linux x64 UID-1000 custody identity.");
        }

        byte[] incumbentBytes = SecureRead(
            options.IncumbentPfx,
            MaximumBundleBytes,
            options.IncumbentPfxSha256,
            "incumbent PKCS#12");
        byte[] freshBytes = SecureRead(
            options.FreshPfx,
            MaximumBundleBytes,
            options.FreshPfxSha256,
            "fresh PKCS#12");
        byte[] passwordBytes = SecureRead(
            options.PasswordFile,
            MaximumPasswordBytes,
            options.PasswordFileSha256,
            "password file");
        byte[]? exportedBytes = null;
        try
        {
            string password = DecodePassword(passwordBytes);
            X509Certificate2Collection incumbent = X509CertificateLoader.LoadPkcs12Collection(
                incumbentBytes,
                password,
                X509KeyStorageFlags.EphemeralKeySet);
            X509Certificate2Collection fresh = X509CertificateLoader.LoadPkcs12Collection(
                freshBytes,
                password,
                X509KeyStorageFlags.EphemeralKeySet);
            X509Certificate2Collection? reopened = null;
            try
            {
                (X509Certificate2Collection combined, Inventory inventory) =
                    BuildAndValidateInventory(incumbent, fresh, DateTime.UtcNow);
                exportedBytes = combined.Export(X509ContentType.Pkcs12, password)
                    ?? throw new CryptographicException("PKCS#12 export returned no bytes.");
                if (exportedBytes.Length is < 1 or > MaximumBundleBytes)
                {
                    throw new InvalidDataException("exported PKCS#12 bundle is unbounded.");
                }

                reopened = X509CertificateLoader.LoadPkcs12Collection(
                    exportedBytes,
                    password,
                    X509KeyStorageFlags.EphemeralKeySet);
                Inventory reopenedInventory = ValidateInventory(
                    reopened,
                    inventory.FreshPrivateFingerprints,
                    DateTime.UtcNow,
                    requireMultiPrivateKey: true);
                if (!inventory.PrivateFingerprints.SetEquals(reopenedInventory.PrivateFingerprints)
                    || inventory.PrimaryFingerprint != reopenedInventory.PrimaryFingerprint
                    || inventory.CertificateCount != reopenedInventory.CertificateCount)
                {
                    throw new CryptographicException(
                        "reopened PKCS#12 inventory differs from the validated export source.");
                }

                string outputSha256 = Convert.ToHexStringLower(SHA256.HashData(exportedBytes));
                SecureNoClobberWrite(options.Output, exportedBytes, outputSha256);
                return new Receipt(
                    "chummer.data-protection.certificate-bundle-materialization/v1",
                    "pass",
                    reopenedInventory.CertificateCount,
                    reopenedInventory.PrivateKeyCertificateCount,
                    reopenedInventory.PrimaryFingerprint,
                    reopenedInventory.Certificates,
                    new OutputReceipt(
                        outputSha256,
                        exportedBytes.Length,
                        "0400",
                        ExpectedOwnerUserId,
                        1));
            }
            finally
            {
                DisposeCertificates(reopened);
                DisposeCertificates(incumbent);
                DisposeCertificates(fresh);
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(incumbentBytes);
            CryptographicOperations.ZeroMemory(freshBytes);
            CryptographicOperations.ZeroMemory(passwordBytes);
            if (exportedBytes is not null)
            {
                CryptographicOperations.ZeroMemory(exportedBytes);
            }
        }
    }

    private static (X509Certificate2Collection Collection, Inventory Inventory)
        BuildAndValidateInventory(
            X509Certificate2Collection incumbent,
            X509Certificate2Collection fresh,
            DateTime utcNow)
    {
        int incumbentPrivateCount = incumbent.Cast<X509Certificate2>()
            .Count(static candidate => candidate.HasPrivateKey);
        int freshPrivateCount = fresh.Cast<X509Certificate2>()
            .Count(static candidate => candidate.HasPrivateKey);
        HashSet<string> incumbentPrivate = PrivateFingerprints(incumbent);
        HashSet<string> freshPrivate = PrivateFingerprints(fresh);
        if (incumbentPrivate.Count == 0
            || freshPrivate.Count == 0
            || incumbentPrivate.Count != incumbentPrivateCount
            || freshPrivate.Count != freshPrivateCount)
        {
            throw new InvalidDataException(
                "incumbent and fresh PKCS#12 inputs must each contain unique private-key custody.");
        }
        if (incumbentPrivate.Overlaps(freshPrivate))
        {
            throw new InvalidDataException(
                "incumbent and fresh PKCS#12 inputs contain duplicate private-key certificate identity.");
        }

        var selected = new Dictionary<string, X509Certificate2>(StringComparer.OrdinalIgnoreCase);
        foreach (X509Certificate2 candidate in incumbent.Cast<X509Certificate2>()
                     .Concat(fresh.Cast<X509Certificate2>()))
        {
            string fingerprint = Fingerprint(candidate);
            if (!selected.TryGetValue(fingerprint, out X509Certificate2? existing)
                || (!existing.HasPrivateKey && candidate.HasPrivateKey))
            {
                selected[fingerprint] = candidate;
            }
        }
        var combined = new X509Certificate2Collection();
        foreach (X509Certificate2 candidate in selected.Values
                     .OrderByDescending(static value => value.HasPrivateKey)
                     .ThenByDescending(static value => value.NotAfter.ToUniversalTime())
                     .ThenBy(Fingerprint, StringComparer.OrdinalIgnoreCase))
        {
            combined.Add(candidate);
        }
        try
        {
            Inventory inventory = ValidateInventory(
                combined,
                freshPrivate,
                utcNow,
                requireMultiPrivateKey: true);
            if (!incumbentPrivate.IsSubsetOf(inventory.PrivateFingerprints)
                || !freshPrivate.IsSubsetOf(inventory.PrivateFingerprints))
            {
                throw new InvalidDataException("combined PKCS#12 lost private-key custody.");
            }
            return (combined, inventory);
        }
        catch
        {
            throw;
        }
    }

    private static Inventory ValidateInventory(
        X509Certificate2Collection certificates,
        HashSet<string> freshPrivateFingerprints,
        DateTime utcNow,
        bool requireMultiPrivateKey)
    {
        if (certificates.Count is < 1 or > MaximumCertificatesInBundle)
        {
            throw new InvalidDataException("PKCS#12 certificate inventory is unbounded.");
        }
        X509Certificate2[] privateCertificates = certificates
            .Cast<X509Certificate2>()
            .Where(static candidate => candidate.HasPrivateKey)
            .ToArray();
        int minimum = requireMultiPrivateKey ? 2 : 1;
        if (privateCertificates.Length < minimum
            || privateCertificates.Length > MaximumPrivateKeyCertificates)
        {
            throw new InvalidDataException("PKCS#12 private-key inventory is not a bounded rotation bundle.");
        }
        HashSet<string> privateFingerprints = PrivateFingerprints(privateCertificates);
        if (privateFingerprints.Count != privateCertificates.Length)
        {
            throw new InvalidDataException("PKCS#12 private-key identities are not unique.");
        }
        foreach (X509Certificate2 certificate in privateCertificates)
        {
            ValidateEncryptionCertificate(certificate);
        }
        DateTime latestExpiry = privateCertificates.Max(
            static candidate => candidate.NotAfter.ToUniversalTime());
        X509Certificate2[] primaryCandidates = privateCertificates
            .Where(candidate => candidate.NotAfter.ToUniversalTime() == latestExpiry)
            .ToArray();
        if (primaryCandidates.Length != 1
            || primaryCandidates[0].NotBefore.ToUniversalTime() > utcNow
            || latestExpiry <= utcNow.AddDays(7))
        {
            throw new InvalidDataException(
                "PKCS#12 primary certificate is not uniquely usable under the PR215 contract.");
        }
        string primaryFingerprint = Fingerprint(primaryCandidates[0]);
        if (!freshPrivateFingerprints.Contains(primaryFingerprint))
        {
            throw new InvalidDataException(
                "the unique latest-expiry primary must come from the fresh PKCS#12 input.");
        }
        CertificateReceipt[] receipts = privateCertificates
            .OrderByDescending(static candidate => candidate.NotAfter.ToUniversalTime())
            .ThenBy(Fingerprint, StringComparer.OrdinalIgnoreCase)
            .Select(candidate => new CertificateReceipt(
                Fingerprint(candidate),
                candidate.NotBefore.ToUniversalTime().ToString("O"),
                candidate.NotAfter.ToUniversalTime().ToString("O"),
                RsaKeySize(candidate),
                Fingerprint(candidate) == primaryFingerprint ? "primary" : "decrypt-only"))
            .ToArray();
        return new Inventory(
            certificates.Count,
            privateCertificates.Length,
            primaryFingerprint,
            privateFingerprints,
            new HashSet<string>(freshPrivateFingerprints, StringComparer.OrdinalIgnoreCase),
            receipts);
    }

    private static HashSet<string> PrivateFingerprints(
        IEnumerable<X509Certificate2> certificates)
        => new(
            certificates.Where(static candidate => candidate.HasPrivateKey).Select(Fingerprint),
            StringComparer.OrdinalIgnoreCase);

    private static void ValidateEncryptionCertificate(X509Certificate2 certificate)
    {
        using RSA? rsa = certificate.GetRSAPrivateKey();
        X509KeyUsageExtension? keyUsage = certificate.Extensions
            .OfType<X509KeyUsageExtension>()
            .SingleOrDefault();
        if (rsa is null
            || rsa.KeySize < 2048
            || (keyUsage is not null
                && (keyUsage.KeyUsages
                    & (X509KeyUsageFlags.KeyEncipherment | X509KeyUsageFlags.DataEncipherment)) == 0))
        {
            throw new InvalidDataException(
                "every private-key certificate must be RSA-2048+ and encryption-capable.");
        }
    }

    private static int RsaKeySize(X509Certificate2 certificate)
    {
        using RSA rsa = certificate.GetRSAPrivateKey()
            ?? throw new InvalidDataException("certificate has no RSA private key.");
        return rsa.KeySize;
    }

    private static string Fingerprint(X509Certificate2 certificate)
        => certificate.GetCertHashString(HashAlgorithmName.SHA256).ToLowerInvariant();

    private static string DecodePassword(byte[] bytes)
    {
        string password = new UTF8Encoding(false, true).GetString(bytes).TrimEnd('\r', '\n');
        if (password.Length is < 1 or > 4096 || password.Any(char.IsControl))
        {
            throw new InvalidDataException("password file must contain one bounded UTF-8 line.");
        }
        return password;
    }

    private static byte[] SecureRead(
        string pathValue,
        int maximumBytes,
        string expectedSha256,
        string label,
        uint expectedMode = 0)
    {
        string path = ExactAbsolutePath(pathValue, label);
        AssertNoSymlinkParents(path, label);
        int descriptor = NativeOpen(path, OpenReadOnly | OpenCloseOnExec | OpenNoFollow);
        if (descriptor < 0)
        {
            throw new IOException($"{label} could not be opened safely.");
        }
        try
        {
            LinuxStat before = DescriptorMetadata(descriptor, label);
            uint mode = before.Mode & 0x1FF;
            if ((before.Mode & FileTypeMask) != RegularFile
                || before.UserId != ExpectedOwnerUserId
                || before.LinkCount != 1
                || before.Size < 1
                || before.Size > maximumBytes
                || (expectedMode == 0
                    ? mode is not (OwnerReadOnlyMode or OwnerReadWriteMode)
                    : mode != expectedMode))
            {
                throw new UnauthorizedAccessException($"{label} metadata is unsafe.");
            }
            byte[] payload = GC.AllocateUninitializedArray<byte>(checked((int)before.Size));
            using (var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: false))
            using (var stream = new FileStream(handle, FileAccess.Read, 64 * 1024, isAsync: false))
            {
                stream.ReadExactly(payload);
            }
            LinuxStat after = DescriptorMetadata(descriptor, label);
            if (!before.SameIdentity(after)
                || NativeLstat(path, out LinuxStat current) != 0
                || !before.SameIdentity(current))
            {
                CryptographicOperations.ZeroMemory(payload);
                throw new IOException($"{label} changed while open.");
            }
            string digest = Convert.ToHexStringLower(SHA256.HashData(payload));
            if (!CryptographicOperations.FixedTimeEquals(
                    Encoding.ASCII.GetBytes(digest),
                    Encoding.ASCII.GetBytes(expectedSha256)))
            {
                CryptographicOperations.ZeroMemory(payload);
                throw new InvalidDataException($"{label} does not match its external SHA-256 pin.");
            }
            return payload;
        }
        finally
        {
            NativeClose(descriptor);
        }
    }

    private static void SecureNoClobberWrite(string pathValue, byte[] payload, string expectedSha256)
    {
        string path = ExactAbsolutePath(pathValue, "output PKCS#12");
        string parentPath = Path.GetDirectoryName(path)
            ?? throw new InvalidDataException("output PKCS#12 has no parent directory.");
        AssertNoSymlinkParents(parentPath, "output PKCS#12 parent");
        int parentDescriptor = NativeOpen(
            parentPath,
            OpenReadOnly | OpenDirectory | OpenCloseOnExec | OpenNoFollow);
        if (parentDescriptor < 0)
        {
            throw new IOException("output PKCS#12 parent could not be opened safely.");
        }
        string outputName = Path.GetFileName(path);
        if (string.IsNullOrEmpty(outputName) || outputName is "." or "..")
        {
            NativeClose(parentDescriptor);
            throw new InvalidDataException("output PKCS#12 name is invalid.");
        }
        string temporaryName = $".{outputName}.{Environment.ProcessId}.{Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(8))}.tmp";
        int outputDescriptor = -1;
        bool temporaryLinked = false;
        try
        {
            LinuxStat parent = DescriptorMetadata(parentDescriptor, "output PKCS#12 parent");
            if ((parent.Mode & FileTypeMask) != DirectoryFile
                || parent.UserId != ExpectedOwnerUserId
                || (parent.Mode & 0x1FF) != OwnerDirectoryMode)
            {
                throw new UnauthorizedAccessException(
                    "output PKCS#12 parent must be a UID-1000 mode-0700 directory.");
            }
            outputDescriptor = NativeOpenAtWithMode(
                parentDescriptor,
                temporaryName,
                OpenWriteOnly | OpenCreate | OpenExclusive | OpenCloseOnExec | OpenNoFollow,
                OwnerReadWriteMode);
            if (outputDescriptor < 0)
            {
                throw new IOException("output PKCS#12 staging file could not be created.");
            }
            using (var handle = new SafeFileHandle((IntPtr)outputDescriptor, ownsHandle: false))
            using (var stream = new FileStream(handle, FileAccess.Write, 64 * 1024, isAsync: false))
            {
                stream.Write(payload);
                stream.Flush(flushToDisk: true);
            }
            if (NativeFchmod(outputDescriptor, OwnerReadOnlyMode) != 0
                || NativeFsync(outputDescriptor) != 0)
            {
                throw new IOException("output PKCS#12 permissions could not be committed.");
            }
            LinuxStat staged = DescriptorMetadata(outputDescriptor, "staged output PKCS#12");
            if ((staged.Mode & FileTypeMask) != RegularFile
                || staged.UserId != ExpectedOwnerUserId
                || (staged.Mode & 0x1FF) != OwnerReadOnlyMode
                || staged.LinkCount != 1
                || staged.Size != payload.Length)
            {
                throw new UnauthorizedAccessException("staged output PKCS#12 metadata is unsafe.");
            }
            if (NativeLinkAt(parentDescriptor, temporaryName, parentDescriptor, outputName, 0) != 0)
            {
                throw new IOException("output PKCS#12 already exists or cannot be installed no-clobber.");
            }
            temporaryLinked = true;
            if (NativeUnlinkAt(parentDescriptor, temporaryName, 0) != 0
                || NativeFsync(parentDescriptor) != 0)
            {
                throw new IOException("output PKCS#12 directory commit failed.");
            }
        }
        finally
        {
            if (outputDescriptor >= 0)
            {
                NativeClose(outputDescriptor);
            }
            if (!temporaryLinked)
            {
                _ = NativeUnlinkAt(parentDescriptor, temporaryName, 0);
            }
            NativeClose(parentDescriptor);
        }
        byte[] installed = SecureRead(
            path,
            MaximumBundleBytes,
            expectedSha256,
            "installed output PKCS#12",
            OwnerReadOnlyMode);
        try
        {
            if (!payload.AsSpan().SequenceEqual(installed))
            {
                throw new IOException("installed output PKCS#12 bytes changed.");
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(installed);
        }
    }

    private static string ExactAbsolutePath(string value, string label)
    {
        if (string.IsNullOrWhiteSpace(value) || !Path.IsPathFullyQualified(value))
        {
            throw new InvalidDataException($"{label} path must be absolute.");
        }
        string fullPath = Path.GetFullPath(value);
        if (!string.Equals(value, fullPath, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} path must be exactly normalized.");
        }
        return fullPath;
    }

    private static void AssertNoSymlinkParents(string path, string label)
    {
        string? current = Path.GetPathRoot(path);
        if (current is null)
        {
            throw new InvalidDataException($"{label} path has no root.");
        }
        string relative = Path.GetRelativePath(current, path);
        string[] components = relative.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries);
        for (int index = 0; index < Math.Max(0, components.Length - 1); index++)
        {
            current = Path.Combine(current, components[index]);
            if (NativeLstat(current, out LinuxStat metadata) != 0
                || (metadata.Mode & FileTypeMask) != DirectoryFile)
            {
                throw new UnauthorizedAccessException($"{label} parent path is unsafe.");
            }
        }
    }

    private static LinuxStat DescriptorMetadata(int descriptor, string label)
    {
        if (NativeFstat(descriptor, out LinuxStat metadata) != 0)
        {
            throw new IOException($"unable to inspect {label} descriptor.");
        }
        return metadata;
    }

    private static void DisposeCertificates(X509Certificate2Collection? certificates)
    {
        if (certificates is null)
        {
            return;
        }
        foreach (X509Certificate2 certificate in certificates)
        {
            certificate.Dispose();
        }
    }

    private sealed record Arguments(
        string IncumbentPfx,
        string IncumbentPfxSha256,
        string FreshPfx,
        string FreshPfxSha256,
        string PasswordFile,
        string PasswordFileSha256,
        string Output)
    {
        public static Arguments Parse(string[] arguments)
        {
            var values = new Dictionary<string, string>(StringComparer.Ordinal);
            if (arguments.Length == 1 && arguments[0] == "--help")
            {
                Console.Out.WriteLine(
                    "usage: Chummer.DataProtectionBundleMaterializer "
                    + "--incumbent-pfx PATH --incumbent-pfx-sha256 HEX "
                    + "--fresh-pfx PATH --fresh-pfx-sha256 HEX "
                    + "--password-file PATH --password-file-sha256 HEX --output PATH");
                Environment.Exit(0);
            }
            if (arguments.Length % 2 != 0)
            {
                throw new ArgumentException("arguments must be explicit option/value pairs.");
            }
            for (int index = 0; index < arguments.Length; index += 2)
            {
                string name = arguments[index];
                string value = arguments[index + 1];
                if (!ExpectedNames.Contains(name) || !values.TryAdd(name, value))
                {
                    throw new ArgumentException("unknown or duplicate argument rejected.");
                }
            }
            if (values.Count != ExpectedNames.Count)
            {
                throw new ArgumentException("every governed bundle input is required.");
            }
            foreach (string name in new[]
                     {
                         "--incumbent-pfx-sha256",
                         "--fresh-pfx-sha256",
                         "--password-file-sha256",
                     })
            {
                if (!Sha256Regex().IsMatch(values[name]))
                {
                    throw new ArgumentException($"{name} must be a lowercase SHA-256.");
                }
            }
            return new Arguments(
                values["--incumbent-pfx"],
                values["--incumbent-pfx-sha256"],
                values["--fresh-pfx"],
                values["--fresh-pfx-sha256"],
                values["--password-file"],
                values["--password-file-sha256"],
                values["--output"]);
        }

        private static readonly HashSet<string> ExpectedNames = new(StringComparer.Ordinal)
        {
            "--incumbent-pfx",
            "--incumbent-pfx-sha256",
            "--fresh-pfx",
            "--fresh-pfx-sha256",
            "--password-file",
            "--password-file-sha256",
            "--output",
        };
    }

    private sealed record Inventory(
        int CertificateCount,
        int PrivateKeyCertificateCount,
        string PrimaryFingerprint,
        HashSet<string> PrivateFingerprints,
        HashSet<string> FreshPrivateFingerprints,
        CertificateReceipt[] Certificates);

    private sealed record Receipt(
        string ContractName,
        string Status,
        int CertificateCount,
        int PrivateKeyCertificateCount,
        string PrimaryFingerprintSha256,
        CertificateReceipt[] Certificates,
        OutputReceipt Output);

    private sealed record CertificateReceipt(
        string FingerprintSha256,
        string NotBeforeUtc,
        string NotAfterUtc,
        int RsaKeySizeBits,
        string Role);

    private sealed record OutputReceipt(
        string Sha256,
        int SizeBytes,
        string Mode,
        uint UserId,
        int LinkCount);

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        WriteIndented = false,
    };

    [GeneratedRegex("^[0-9a-f]{64}$", RegexOptions.CultureInvariant)]
    private static partial Regex Sha256Regex();

    [StructLayout(LayoutKind.Sequential)]
    private struct LinuxStat
    {
        public ulong Device;
        public ulong Inode;
        public ulong LinkCount;
        public uint Mode;
        public uint UserId;
        public uint GroupId;
        public int Padding;
        public ulong SpecialDevice;
        public long Size;
        public long BlockSize;
        public long Blocks;
        public long AccessSeconds;
        public long AccessNanoseconds;
        public long ModifiedSeconds;
        public long ModifiedNanoseconds;
        public long ChangedSeconds;
        public long ChangedNanoseconds;
        public long Reserved0;
        public long Reserved1;
        public long Reserved2;

        public readonly bool SameIdentity(LinuxStat other)
            => Device == other.Device
                && Inode == other.Inode
                && LinkCount == other.LinkCount
                && Mode == other.Mode
                && UserId == other.UserId
                && Size == other.Size
                && ModifiedSeconds == other.ModifiedSeconds
                && ModifiedNanoseconds == other.ModifiedNanoseconds
                && ChangedSeconds == other.ChangedSeconds
                && ChangedNanoseconds == other.ChangedNanoseconds;
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "openat", SetLastError = true)]
    private static extern int NativeOpenAtWithMode(int directoryDescriptor, string path, int flags, uint mode);

    [DllImport("libc", EntryPoint = "fstat", SetLastError = true)]
    private static extern int NativeFstat(int descriptor, out LinuxStat metadata);

    [DllImport("libc", EntryPoint = "lstat", SetLastError = true)]
    private static extern int NativeLstat(string path, out LinuxStat metadata);

    [DllImport("libc", EntryPoint = "fchmod", SetLastError = true)]
    private static extern int NativeFchmod(int descriptor, uint mode);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int descriptor);

    [DllImport("libc", EntryPoint = "linkat", SetLastError = true)]
    private static extern int NativeLinkAt(
        int oldDirectoryDescriptor,
        string oldPath,
        int newDirectoryDescriptor,
        string newPath,
        int flags);

    [DllImport("libc", EntryPoint = "unlinkat", SetLastError = true)]
    private static extern int NativeUnlinkAt(int directoryDescriptor, string path, int flags);

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int NativeClose(int descriptor);

    [DllImport("libc", EntryPoint = "geteuid")]
    private static extern uint NativeGetEffectiveUserId();
}
