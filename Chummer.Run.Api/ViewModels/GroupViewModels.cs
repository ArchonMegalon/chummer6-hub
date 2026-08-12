using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.ViewModels;

public sealed record GroupListPageViewModel(
    SiteChromeViewModel Chrome,
    string SignedInLabel,
    IReadOnlyList<GroupDto> Groups,
    string? Notice,
    bool FocusChronicles = false);

public sealed record GroupDetailPageViewModel(
    SiteChromeViewModel Chrome,
    GroupDto Group,
    IReadOnlyList<JoinCodeDto> JoinCodes,
    IReadOnlyList<ChronicleProjectDto> ChronicleProjects,
    bool CanManage,
    string? Notice);

public sealed record GroupJoinPageViewModel(
    SiteChromeViewModel Chrome,
    GroupDto Group,
    JoinCodeDto Invite,
    IReadOnlyList<RunnerDossierProjection> Runners,
    string? SelectedDossierId,
    string? Notice);
