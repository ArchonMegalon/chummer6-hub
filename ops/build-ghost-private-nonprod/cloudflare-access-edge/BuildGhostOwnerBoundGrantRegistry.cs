using System.Security.Cryptography;
using System.Text;

namespace Chummer.BuildGhost.CloudflareAccessEdge;

/// <summary>
/// Fail-closed, process-local binding between a grant observed at the Access
/// issuance boundary and the validated Access owner allowed to dispatch it.
/// Raw packet keys are never retained. A restart deliberately invalidates all
/// outstanding Access-side bindings while the Presentation authority remains
/// the final one-use/expiry/revocation authority.
/// </summary>
public sealed class BuildGhostOwnerBoundGrantRegistry
{
    public const int MaximumBindings = 4096;
    public static readonly TimeSpan MaximumGrantLifetime = TimeSpan.FromMinutes(5);

    private readonly object _gate = new();
    private readonly Dictionary<string, OwnerBoundGrant> _bindings = new(StringComparer.Ordinal);
    private readonly TimeProvider _timeProvider;

    public BuildGhostOwnerBoundGrantRegistry(TimeProvider timeProvider)
    {
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
    }

    public bool TryRegister(
        string packetAccessKey,
        string owner,
        string packetDigest,
        DateTimeOffset expiresAtUtc)
    {
        if (!BuildGhostProviderToolRequestContract.IsCanonicalPacketAccessKey(packetAccessKey)
            || !BuildGhostProviderToolRequestContract.IsCanonicalPacketDigest(packetDigest)
            || string.IsNullOrWhiteSpace(owner))
        {
            return false;
        }

        DateTimeOffset now = _timeProvider.GetUtcNow();
        if (expiresAtUtc <= now
            || expiresAtUtc > now.Add(MaximumGrantLifetime))
        {
            return false;
        }

        string keyRef = KeyReference(packetAccessKey);
        lock (_gate)
        {
            RemoveExpiredUnderLock(now);
            if (_bindings.Count >= MaximumBindings || _bindings.ContainsKey(keyRef))
            {
                return false;
            }

            _bindings.Add(keyRef, new OwnerBoundGrant(
                OwnerReference(owner),
                packetDigest,
                expiresAtUtc));
            return true;
        }
    }

    public bool TryClaim(
        string packetAccessKey,
        string owner,
        string packetDigest)
    {
        if (!BuildGhostProviderToolRequestContract.IsCanonicalPacketAccessKey(packetAccessKey)
            || !BuildGhostProviderToolRequestContract.IsCanonicalPacketDigest(packetDigest))
        {
            return false;
        }

        DateTimeOffset now = _timeProvider.GetUtcNow();
        string keyRef = KeyReference(packetAccessKey);
        lock (_gate)
        {
            RemoveExpiredUnderLock(now);
            if (!_bindings.TryGetValue(keyRef, out OwnerBoundGrant? binding)
                || binding is null
                || !FixedEquals(binding.OwnerReference, OwnerReference(owner))
                || !FixedEquals(binding.PacketDigest, packetDigest))
            {
                return false;
            }

            // Claim before network dispatch. A timeout or crash may sacrifice
            // availability for this grant, but can never dispatch it twice.
            _bindings.Remove(keyRef);
            return true;
        }
    }

    public int Count
    {
        get
        {
            lock (_gate)
            {
                RemoveExpiredUnderLock(_timeProvider.GetUtcNow());
                return _bindings.Count;
            }
        }
    }

    private void RemoveExpiredUnderLock(DateTimeOffset now)
    {
        foreach (string key in _bindings
                     .Where(pair => pair.Value.ExpiresAtUtc <= now)
                     .Select(static pair => pair.Key)
                     .ToArray())
        {
            _bindings.Remove(key);
        }
    }

    private static string KeyReference(string packetAccessKey)
    {
        byte[] material = Encoding.ASCII.GetBytes(packetAccessKey);
        try
        {
            return Convert.ToHexString(SHA256.HashData(material)).ToLowerInvariant();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(material);
        }
    }

    private static string OwnerReference(string owner)
    {
        byte[] material = Encoding.UTF8.GetBytes($"build-ghost-access-owner-v1\n{owner}");
        try
        {
            return Convert.ToHexString(SHA256.HashData(material)).ToLowerInvariant();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(material);
        }
    }

    private static bool FixedEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        try
        {
            return leftBytes.Length == rightBytes.Length
                && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(leftBytes);
            CryptographicOperations.ZeroMemory(rightBytes);
        }
    }

    private sealed record OwnerBoundGrant(
        string OwnerReference,
        string PacketDigest,
        DateTimeOffset ExpiresAtUtc);
}
