using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Privacy;

public static class AccountErasureConfirmation
{
    public const string RequiredPhrase = "ERASE MY CHUMMER ACCOUNT";
}

public sealed record EraseCurrentAccountRequest(
    [Required(AllowEmptyStrings = false), StringLength(32)] string Confirmation);

public sealed record AccountErasureComponentReceipt(
    string Component,
    bool Completed,
    int RecordsRemoved,
    string ReceiptSha256);

public sealed record CurrentAccountErasureResponse(
    bool Erased,
    string SubjectKeySha256,
    string? UserKeySha256,
    IReadOnlyList<AccountErasureComponentReceipt> Components,
    DateTimeOffset ErasedAtUtc,
    string ReceiptSha256);
