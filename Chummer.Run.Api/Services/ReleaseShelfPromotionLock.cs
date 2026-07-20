namespace Chummer.Run.Api.Services;

public sealed class ReleaseShelfMutationConcurrencyException : InvalidOperationException
{
    public ReleaseShelfMutationConcurrencyException(string message)
        : base(message)
    {
    }

    public ReleaseShelfMutationConcurrencyException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}

/// <summary>
/// The single cross-process mutation lock for release-shelf activation and
/// same-generation release-authority advancement. Keeping both mutations on
/// one lock prevents an authority compare-and-swap from racing a shelf
/// promotion or rollback.
/// </summary>
internal static class ReleaseShelfPromotionLock
{
    internal const string FileName = ".release-shelf-promotion.lock";

    internal static FileStream Acquire(string downloadsRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(downloadsRoot);
        string lockPath = Path.Combine(downloadsRoot, FileName);
        try
        {
            var options = new FileStreamOptions
            {
                Mode = FileMode.OpenOrCreate,
                Access = FileAccess.ReadWrite,
                Share = FileShare.None
            };
            if (!OperatingSystem.IsWindows())
            {
                options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
            }

            FileStream promotionLock = new(lockPath, options);
            try
            {
                if (!OperatingSystem.IsWindows())
                {
                    File.SetUnixFileMode(
                        lockPath,
                        UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }

                return promotionLock;
            }
            catch
            {
                promotionLock.Dispose();
                throw;
            }
        }
        catch (IOException ex)
        {
            throw new ReleaseShelfMutationConcurrencyException(
                "another release shelf mutation is already in progress.",
                ex);
        }
    }
}
