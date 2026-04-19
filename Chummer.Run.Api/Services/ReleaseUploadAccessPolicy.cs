namespace Chummer.Run.Api.Services;

public static class ReleaseUploadAccessPolicy
{
    public const string AllowedEmail = "tibor.girschele@gmail.com";

    public static bool CanAccess(string? email)
        => !string.IsNullOrWhiteSpace(email)
           && string.Equals(email.Trim(), AllowedEmail, StringComparison.OrdinalIgnoreCase);
}
