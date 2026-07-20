namespace Chummer.Run.Api.Services;

/// <summary>
/// Immutable operator intent for the complete incoming desktop release shelf.
/// Tuple ids use the canonical head:platform:rid order. The derived Registry
/// floor projections are persisted too and revalidated whenever session state
/// is loaded so a partial metadata edit cannot silently change release scope.
/// </summary>
public sealed record ReleaseDesktopTupleScope(
    IReadOnlyList<string> TupleIds,
    IReadOnlyList<string> RequiredPlatforms,
    IReadOnlyList<string> RequiredHeads,
    IReadOnlyList<string> RequiredPlatformHeadRidTuples)
{
    private const int MaximumScopeCharacters = 4096;
    private const int MaximumTupleCount = 32;
    private const int MaximumTokenCharacters = 64;

    public static ReleaseDesktopTupleScope Parse(string value)
    {
        if (value is null)
        {
            throw new InvalidDataException("exact incoming desktop scope is required when declared.");
        }
        if (value.Length is 0 or > MaximumScopeCharacters)
        {
            throw new InvalidDataException(
                $"exact incoming desktop scope must contain 1 through {MaximumScopeCharacters} characters.");
        }

        return FromTupleIds(value.Split(',', StringSplitOptions.None));
    }

    public static ReleaseDesktopTupleScope FromTupleIds(IEnumerable<string> values)
    {
        ArgumentNullException.ThrowIfNull(values);
        string[] rawValues = values.ToArray();
        if (rawValues.Length is 0 or > MaximumTupleCount)
        {
            throw new InvalidDataException(
                $"exact incoming desktop scope must declare 1 through {MaximumTupleCount} tuples.");
        }

        var tupleIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (string rawValue in rawValues)
        {
            string[] parts = (rawValue ?? string.Empty).Split(':', StringSplitOptions.None);
            if (parts.Length != 3)
            {
                throw new InvalidDataException(
                    $"exact incoming desktop tuple must use head:platform:rid: {rawValue}");
            }

            string head = NormalizeToken(parts[0]);
            string platform = NormalizePlatform(parts[1]);
            string rid = NormalizeToken(parts[2]);
            if (!IsSafeToken(head) || !IsSafeToken(platform) || !IsSafeToken(rid))
            {
                throw new InvalidDataException(
                    $"exact incoming desktop tuple contains an invalid token: {rawValue}");
            }

            string tupleId = $"{head}:{platform}:{rid}";
            if (!tupleIds.Add(tupleId))
            {
                throw new InvalidDataException(
                    $"exact incoming desktop tuple was declared more than once: {tupleId}");
            }
        }

        string[] canonicalTupleIds = tupleIds.Order(StringComparer.Ordinal).ToArray();
        if (string.Join(',', canonicalTupleIds).Length > MaximumScopeCharacters)
        {
            throw new InvalidDataException(
                $"exact incoming desktop scope must contain at most {MaximumScopeCharacters} characters.");
        }
        string[] requiredPlatforms = canonicalTupleIds
            .Select(static value => value.Split(':', StringSplitOptions.None)[1])
            .Distinct(StringComparer.Ordinal)
            .Order(StringComparer.Ordinal)
            .ToArray();
        string[] requiredHeads = canonicalTupleIds
            .Select(static value => value.Split(':', StringSplitOptions.None)[0])
            .Distinct(StringComparer.Ordinal)
            .Order(StringComparer.Ordinal)
            .ToArray();
        string[] requiredPlatformHeadRidTuples = canonicalTupleIds
            .Select(static value =>
            {
                string[] parts = value.Split(':', StringSplitOptions.None);
                return $"{parts[0]}:{parts[2]}:{parts[1]}";
            })
            .Order(StringComparer.Ordinal)
            .ToArray();

        return new ReleaseDesktopTupleScope(
            canonicalTupleIds,
            requiredPlatforms,
            requiredHeads,
            requiredPlatformHeadRidTuples);
    }

    public void ValidateCanonical()
    {
        if (TupleIds is null
            || RequiredPlatforms is null
            || RequiredHeads is null
            || RequiredPlatformHeadRidTuples is null)
        {
            throw new InvalidDataException("exact incoming desktop scope metadata is incomplete.");
        }

        ReleaseDesktopTupleScope canonical = FromTupleIds(TupleIds);
        if (!TupleIds.SequenceEqual(canonical.TupleIds, StringComparer.Ordinal)
            || !RequiredPlatforms.SequenceEqual(canonical.RequiredPlatforms, StringComparer.Ordinal)
            || !RequiredHeads.SequenceEqual(canonical.RequiredHeads, StringComparer.Ordinal)
            || !RequiredPlatformHeadRidTuples.SequenceEqual(
                canonical.RequiredPlatformHeadRidTuples,
                StringComparer.Ordinal))
        {
            throw new InvalidDataException("exact incoming desktop scope metadata is not canonical.");
        }
    }

    public bool SemanticallyEquals(ReleaseDesktopTupleScope? other)
        => other is not null
           && TupleIds.SequenceEqual(other.TupleIds, StringComparer.Ordinal);

    public string ToTransport()
    {
        ValidateCanonical();
        return string.Join(',', TupleIds);
    }

    public static ReleaseDesktopTupleScope? ParseOptionalCanonical(string? value)
    {
        if (value is null)
        {
            return null;
        }

        ReleaseDesktopTupleScope scope = Parse(value);
        if (!string.Equals(scope.ToTransport(), value, StringComparison.Ordinal))
        {
            throw new InvalidDataException("exact incoming desktop scope receipt is not canonical.");
        }

        return scope;
    }

    private static string NormalizeToken(string value)
        => (value ?? string.Empty).Trim().ToLowerInvariant();

    private static string NormalizePlatform(string value)
        => NormalizeToken(value) switch
        {
            "win" => "windows",
            "windows" => "windows",
            "mac" => "macos",
            "macos" => "macos",
            "osx" => "macos",
            "linux" => "linux",
            string token => token
        };

    private static bool IsSafeToken(string value)
        => value.Length is > 0 and <= MaximumTokenCharacters
           && value.All(static character =>
               character is >= 'a' and <= 'z'
                   or >= '0' and <= '9'
                   or '.' or '_' or '+' or '-');
}
