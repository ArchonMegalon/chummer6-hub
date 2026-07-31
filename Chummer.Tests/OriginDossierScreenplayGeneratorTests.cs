using Chummer.Media.Contracts;
using Chummer.Run.Api.Services.Community;
using Xunit;

namespace Chummer.Tests;

public sealed class OriginDossierScreenplayGeneratorTests : IDisposable
{
    private readonly string _root = Path.Combine(
        Path.GetTempPath(),
        "chummer-origin-screenplay-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public void GeneratorBuildsInteractiveActionSceneWithFixedContinuity()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 8 — Nobody Left in the Rain

            At dusk, rain silvered the clinic windows while Kestrel carried the evidence
            case through the crowded treatment room. Vela blocked the rear door and
            pointed toward the service corridor before the patrol reached the street.

            "You're tracking mud inside," Vela said.
            "I can wipe my boots," Kestrel said.
            "Then move before they see the case," Vela warned.
            "Cover the corridor and stay with me," Kestrel replied.

            Kestrel pulled the case away from a reaching drone arm. Vela struck the
            emergency shutter control, caught the falling case, and shoved it back across
            the counter. Together they crossed the same room while the dusk rain hammered
            the same windows and the approaching patrol lights swept the street outside.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath);

        OriginDossierScreenplayPlan plan =
            OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27);

        Assert.Equal(OriginDossierScreenplayContract.Version, plan.ContractVersion);
        Assert.Equal("continuous dusk", plan.TimeOfDay);
        Assert.Equal("the same continuous rain", plan.Weather);
        Assert.Equal(27, plan.PlannedShotCount);
        Assert.Contains(plan.Cast, character => character.Name == "Kestrel");
        Assert.Contains(plan.Cast, character => character.Name == "Vela");
        Assert.True(plan.Cast.Count >= 2);
        Assert.True(plan.RenderBeats.Count >= 2);
        Assert.All(plan.RenderBeats, beat =>
        {
            Assert.True(beat.Length <= 281);
            Assert.DoesNotContain("tracking mud", beat, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("wipe my boots", beat, StringComparison.OrdinalIgnoreCase);
        });
        Assert.True(
            plan.DialogueTurns.Count
            >= OriginDossierMediaDispatchContract.MinimumCinematicDialogueTurns);
        Assert.All(
            plan.DialogueTurns,
            turn =>
            {
                Assert.Contains(plan.Cast, character => character.Name == turn.Speaker);
                Assert.Contains(plan.Cast, character => character.Name == turn.Listener);
                Assert.NotEqual(turn.Speaker, turn.Listener);
                Assert.True(OriginDossierScreenplayContract.IsDialogueTurnRenderable(turn.Line));
            });
        Assert.Equal(64, plan.FingerprintSha256.Length);
        Assert.True(OriginDossierScreenplayContract.FingerprintMatches(request, plan));
    }

    [Fact]
    public void GeneratorUsesFocusedCanonDialogueWhenSelectedChapterIsDialogueLight()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 2 — The Clinic

            Vela: You're tracking mud inside.
            Kestrel said, "I can wipe my boots."
            "Step in before the rain follows you," Vela warns.
            Kestrel: I remember what I owe.

            # Chapter 8 — Nobody Left in the Rain

            Kestrel stood at Vela's clinic door and remembered the old debt as the patrol
            crossed the wet street. Vela opened the service corridor, pulled Kestrel out
            of the patrol's line of sight, and helped carry the evidence case to safety.
            The selected chapter holds on their shared objective, physical movement,
            reaction, consequence, and the choice that resolves the scene together.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath);

        OriginDossierScreenplayPlan plan =
            OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27);

        Assert.True(plan.UsesSupportingCanonDialogue);
        Assert.Contains(
            plan.DialogueTurns,
            turn => turn.Line.Contains("tracking mud", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(
            plan.DialogueTurns,
            turn => turn.Speaker == "Vela"
                && turn.Listener == "Kestrel"
                && turn.UsesSupportingCanonDialogue);
        Assert.All(plan.DialogueTurns, turn => Assert.True(turn.UsesSupportingCanonDialogue));
        Assert.True(
            plan.DialogueTurns.Count
            >= OriginDossierMediaDispatchContract.MinimumCinematicDialogueTurns);
    }

    [Fact]
    public void GeneratorKeepsLocationsOutOfCastAndUsesOneCoherentSupportingExchange()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 2 — The Clinic Threshold

            Redmond rain ran down the clinic door while Kestrel faced Vela across the
            same cramped treatment room. The old medical monitor waited beside them.

            ## The Price of Speed

            "You're tracking mud inside," Vela said.
            "I can wipe my boots," Kestrel said.
            "You've been staring at it since you walked in," Vela said.
            "I don't need smooth," Kestrel said.
            "You're nineteen," Vela said.
            "I'm still alive," Kestrel said.
            "Installation is a risk," Vela said.
            "I pay my debts," Kestrel said.

            ## Under the Collarbone

            "Strap your arms down," Vela said.
            "Count backward from ten," Vela said.
            "Ten," Kestrel said.
            "Don't move," Vela said.

            Vela caught the falling instrument tray. Kestrel steadied it, crossed the
            room with her, and closed the same door against the continuous night rain.

            # Chapter 8 — Nobody Left in the Rain

            Kestrel stood at Vela's half-lit street clinic door while Redmond rain ran
            from her jacket. Vela waited inside beside the surgical chair. Kestrel's
            right hand trembled when the old medical monitor chirped, then steadied.
            Kestrel crossed the threshold, faced Vela, and together they moved the old
            rig clear of the leaking doorway before Kestrel returned to the night rain.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath) with
        {
            SelectionId = "scene-clinic-door-rain",
            SelectionLabel = "Chapter 8 — Clinic Door in the Rain",
            SelectionSummary = "Kestrel stands at Vela's half-lit street-clinic door in Redmond rain; an old medical monitor chirps, her right hand trembles, she steadies it, and steps back into the rain without false closure."
        };

        OriginDossierScreenplayPlan plan =
            OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27);

        Assert.Equal(2, plan.Cast.Count);
        Assert.Contains(plan.Cast, character => character.Name == "Kestrel");
        Assert.Contains(plan.Cast, character => character.Name == "Vela");
        Assert.DoesNotContain(plan.Cast, character => character.Name == "Redmond");
        Assert.Equal(8, plan.DialogueTurns.Count);
        Assert.Contains(
            "tracking mud",
            plan.DialogueTurns[0].Line,
            StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(
            plan.DialogueTurns,
            turn => string.Equals(turn.Line, "Ten.", StringComparison.OrdinalIgnoreCase));
        Assert.Equal(
            new[] { "Kestrel", "Vela" },
            plan.DialogueTurns
                .Select(turn => turn.Speaker)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(name => name, StringComparer.OrdinalIgnoreCase));
        Assert.All(plan.DialogueTurns, turn =>
        {
            Assert.True(turn.UsesSupportingCanonDialogue);
            Assert.DoesNotMatch("[,;:—-]$", turn.Line);
            Assert.True(OriginDossierScreenplayContract.IsDialogueTurnRenderable(turn.Line));
        });
    }

    [Fact]
    public void GeneratorLocksTheFirstSceneAnchorsInsteadOfSemanticPriority()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 8 — The Clockwork Exchange

            At night, fog filled the loading bay while Kestrel handed Vela the sealed
            case. They knew the rain would arrive by dawn, but the exchange had to end
            before either later condition could change the scene around them.

            "Keep the case level," Vela said.
            "Then clear the gate," Kestrel replied.
            "The lock is moving," Vela warned.
            "Stay on my side of the line," Kestrel said.

            Kestrel caught the gate as it dropped. Vela pulled the case through, blocked
            the scanner arm, and held the same position until Kestrel crossed beside her.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath);

        OriginDossierScreenplayPlan plan =
            OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27);

        Assert.Equal("continuous night", plan.TimeOfDay);
        Assert.Equal("the same continuous fog", plan.Weather);
    }

    [Fact]
    public void GeneratorFailsClosedInsteadOfInventingASecondCharacter()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 8 — Solitary Transit

            At night, the lone traveler crossed the warehouse and checked every locked
            door. Four recorded phrases played over an abandoned intercom while nobody
            answered and no second person entered the physical scene.

            "Proceed to the marked exit."
            "Keep the access card visible."
            "Wait for the status lamp."
            "Leave the door secured."

            The traveler completed the route alone, carried the case outside, and never
            met or interacted with another character anywhere in the selected chapter.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath);

        InvalidOperationException error = Assert.Throws<InvalidOperationException>(
            () => OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27));

        Assert.Equal("origin_dossier_media_screenplay_cast_missing", error.Message);
    }

    [Fact]
    public void GeneratorFailsClosedWhenNoChapterScaleDialogueExists()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 8 — Silent Corridor

            Kestrel crossed a long silent corridor alone. The prose contains enough
            physical description to qualify as a narrative beat, but nobody speaks and
            no earlier canon dialogue exists for a multi-character chapter adaptation.
            The corridor remains quiet while the character reaches the far door and
            leaves without meeting another person or exchanging any spoken words.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath);

        InvalidOperationException error = Assert.Throws<InvalidOperationException>(
            () => OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27));

        Assert.Equal("origin_dossier_media_chapter_dialogue_missing", error.Message);
    }

    [Fact]
    public void GeneratorFailsClosedWhenCanonicalDialogueCannotFitNaturalShotPacing()
    {
        string manuscriptPath = WriteManuscript(
            """
            # Chapter 8 — The Overwritten Exchange

            At night, Kestrel and Vela crossed the loading bay together, moved the case
            around a closing security gate, and held the same positions while the patrol
            approached through rain beyond the windows.

            "This intentionally overlong canonical sentence contains far too many spoken words to fit naturally inside one coherent cinematic shot," Vela said.
            "Another intentionally overlong canonical sentence keeps talking long after any listener reaction could remain visible in the same shot," Kestrel replied.
            "A third deliberately excessive line continues beyond the practical timing budget established for a natural exchange between two visible characters," Vela warned.
            "The fourth deliberately oversized reply also refuses to leave enough screen time for action, breath, eyeline, and a motivated listener reaction," Kestrel said.

            Kestrel stopped the falling gate while Vela pulled the case clear. They
            crossed the same bay together and resolved the immediate threat without a
            location change, flashback, or break in the weather.
            """);
        OriginDossierMediaDispatchRequest request = BuildRequest(manuscriptPath);

        InvalidOperationException error = Assert.Throws<InvalidOperationException>(
            () => OriginDossierScreenplayGenerator.GenerateFromManuscript(request, 27));

        Assert.Equal("origin_dossier_media_chapter_dialogue_too_long", error.Message);
    }

    private string WriteManuscript(string content)
    {
        Directory.CreateDirectory(_root);
        string path = Path.Combine(_root, "story.md");
        File.WriteAllText(path, content);
        return path;
    }

    private static OriginDossierMediaDispatchRequest BuildRequest(string manuscriptPath)
    {
        OriginDossierMediaDispatchRequest request = new(
            ContractVersion: OriginDossierMediaDispatchContract.Version,
            RequestId: string.Empty,
            Kind: OriginDossierMediaDispatchKind.CinematicScene,
            ProjectId: "origin-screenplay-test",
            OwnerRefHash: new string('a', 64),
            ApprovedOriginPacketId: "packet-screenplay",
            OriginRevisionId: new string('b', 64),
            Source: "chummer6-hub",
            RequestedAtUtc: DateTimeOffset.UtcNow,
            Locale: "en-US",
            SelectionId: "chapter-8",
            SelectionLabel: "Chapter 8 — Nobody Left in the Rain",
            SelectionSummary: "Kestrel and Vela move evidence through the street clinic.",
            ManuscriptPath: manuscriptPath,
            SourcePacketPath: manuscriptPath,
            CoverPath: null,
            SequencePlanPath: null,
            DurationTargetSeconds: OriginDossierMediaDispatchContract.DefaultCinematicDurationSeconds,
            RenderScope: OriginDossierMediaDispatchContract.ChapterRenderScope,
            DialogueRequired: true,
            MinimumDialogueTurns: OriginDossierMediaDispatchContract.MinimumCinematicDialogueTurns);
        return request with
        {
            RequestId = OriginDossierMediaDispatchContract.BuildRequestId(
                request.Kind,
                request.ProjectId,
                request.OwnerRefHash,
                request.SelectionId,
                request.OriginRevisionId)
        };
    }

    public void Dispose()
    {
        if (Directory.Exists(_root))
        {
            Directory.Delete(_root, recursive: true);
        }
    }
}
