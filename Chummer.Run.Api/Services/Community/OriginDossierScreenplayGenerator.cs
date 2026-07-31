using Chummer.Media.Contracts;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services.Community;

internal static class OriginDossierScreenplayGenerator
{
    internal const string Version = OriginDossierScreenplayContract.Version;

    private static readonly HashSet<string> CharacterStopWords = new(
        [
            "After", "Before", "Chapter", "Clinic", "Continuity", "Counterpart",
            "Day", "Door", "Dossier", "Evening", "Inside", "Morning", "Movie",
            "Night", "Nobody", "Origin", "Outside", "Rain", "Redmond", "Runner", "Scene",
            "Selected", "Street", "The", "Their", "Then", "They", "This", "When",
            "Where", "With", "He", "Her", "Hers", "Him", "His", "I", "It", "Its",
            "Me", "Mine", "Our", "Ours", "She", "Them", "Theirs", "Us", "We", "You",
            "Your", "Yours"
        ],
        StringComparer.OrdinalIgnoreCase);

    private static readonly HashSet<string> SupportingDialogueStopWords = new(
        [
            "Chapter", "Clinic", "Door", "Rain", "Scene", "Selected", "The",
            "Inside", "Outside", "When", "Their", "With", "From", "Redmond"
        ],
        StringComparer.OrdinalIgnoreCase);

    internal static OriginDossierScreenplayPlan GenerateFromManuscript(
        OriginDossierMediaDispatchRequest request,
        int plannedShotCount)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (!string.Equals(
                request.RenderScope,
                OriginDossierMediaDispatchContract.ChapterRenderScope,
                StringComparison.Ordinal)
            || !request.DialogueRequired
            || request.MinimumDialogueTurns < OriginDossierMediaDispatchContract.MinimumCinematicDialogueTurns)
        {
            throw new InvalidOperationException("origin_dossier_media_chapter_dialogue_contract_invalid");
        }

        string manuscript = File.ReadAllText(request.ManuscriptPath);
        string chapter = ExtractSelectedChapter(manuscript, request);
        IReadOnlyList<string> beats = ExtractNarrativeBeats(chapter);
        IReadOnlyList<string> chapterDialogueTurns = ExtractDialogueTurns(chapter);
        var dialogueTurns = chapterDialogueTurns.ToList();
        if (dialogueTurns.Count < request.MinimumDialogueTurns)
        {
            IReadOnlyList<string> supportingDialogue =
                ExtractSupportingDialogueTurns(manuscript, request);
            if (supportingDialogue.Count >= request.MinimumDialogueTurns)
            {
                dialogueTurns = supportingDialogue.ToList();
            }
            else
            {
                foreach (string supportingTurn in supportingDialogue)
                {
                    if (!dialogueTurns.Contains(supportingTurn, StringComparer.OrdinalIgnoreCase))
                    {
                        dialogueTurns.Add(supportingTurn);
                    }

                    if (dialogueTurns.Count >= request.MinimumDialogueTurns)
                    {
                        break;
                    }
                }
            }
        }

        if (beats.Count == 0)
        {
            throw new InvalidOperationException("origin_dossier_media_chapter_beats_missing");
        }

        if (dialogueTurns.Count < request.MinimumDialogueTurns)
        {
            throw new InvalidOperationException("origin_dossier_media_chapter_dialogue_missing");
        }

        IReadOnlyList<string> selectedDialogue = SelectDialogueForScreenplay(
            dialogueTurns,
            request.MinimumDialogueTurns,
            plannedShotCount);
        HashSet<string> selectedChapterDialogue = chapterDialogueTurns
            .Select(Normalize)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        return Generate(
            request,
            chapter,
            beats,
            selectedDialogue,
            manuscript,
            selectedChapterDialogue,
            plannedShotCount);
    }

    internal static OriginDossierScreenplayPlan Generate(
        OriginDossierMediaDispatchRequest request,
        string chapter,
        IReadOnlyList<string> narrativeBeats,
        IReadOnlyList<string> dialogueLines,
        string dialogueAttributionSource,
        IReadOnlySet<string> selectedChapterDialogue,
        int plannedShotCount)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentException.ThrowIfNullOrWhiteSpace(chapter);
        if (narrativeBeats.Count == 0)
        {
            throw new InvalidOperationException("origin_dossier_media_screenplay_beats_missing");
        }

        if (dialogueLines.Count < request.MinimumDialogueTurns)
        {
            throw new InvalidOperationException("origin_dossier_media_screenplay_dialogue_missing");
        }
        if (plannedShotCount < request.MinimumDialogueTurns + 2 || plannedShotCount > 180)
        {
            throw new InvalidOperationException("origin_dossier_media_screenplay_shot_count_invalid");
        }

        IReadOnlyDictionary<string, string> explicitSpeakers =
            ExtractExplicitSpeakerAttributions(dialogueAttributionSource);
        IReadOnlyList<string> castNames = ExtractCastNames(
            $"{request.SelectionLabel}\n{request.SelectionSummary}\n{chapter}",
            explicitSpeakers,
            dialogueLines);
        if (castNames.Count < 2)
        {
            throw new InvalidOperationException("origin_dossier_media_screenplay_cast_missing");
        }

        var cast = castNames
            .Select((name, index) => new OriginDossierScreenplayCharacter(
                Name: name,
                Role: index == 0 ? "scene protagonist" : index == 1 ? "scene counterpart" : "supporting character",
                VisualAnchor:
                    $"the same adult {name}, with unchanged face, hair, build, wardrobe, and carried gear"))
            .ToArray();
        IReadOnlyList<OriginDossierScreenplayDialogueTurn> dialogue = AttributeDialogue(
            dialogueLines,
            cast,
            explicitSpeakers,
            selectedChapterDialogue);
        string timeOfDay = ResolveTimeOfDay(chapter);
        string weather = ResolveWeather(chapter);
        string location = ResolveLocation(request);
        string wardrobe = "the exact wardrobe and carried gear established in the opening master shot";
        string screenDirection =
            $"{cast[0].Name} keeps the opening screen direction; {cast[1].Name} stays on the opposite eyeline unless a visible crossing motivates a change";
        var plan = new OriginDossierScreenplayPlan(
            ContractVersion: Version,
            Title: request.SelectionLabel,
            RenderScope: OriginDossierMediaDispatchContract.ChapterRenderScope,
            TimeOfDay: timeOfDay,
            Weather: weather,
            PrimaryLocation: location,
            WardrobeContinuity: wardrobe,
            ScreenDirectionContinuity: screenDirection,
            Cast: cast,
            RenderBeats: narrativeBeats,
            DialogueTurns: dialogue,
            UsesSupportingCanonDialogue: dialogue.Any(turn => turn.UsesSupportingCanonDialogue),
            PlannedShotCount: Math.Max(plannedShotCount, 1),
            FingerprintSha256: string.Empty);
        return plan with
        {
            FingerprintSha256 = OriginDossierScreenplayContract.BuildFingerprint(request, plan)
        };
    }

    private static IReadOnlyList<string> ExtractCastNames(
        string source,
        IReadOnlyDictionary<string, string> explicitSpeakers,
        IReadOnlyList<string> dialogueLines)
    {
        var scores = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var attributedSpeakerNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string dialogueLine in dialogueLines)
        {
            if (explicitSpeakers.TryGetValue(Normalize(dialogueLine), out string? speaker))
            {
                attributedSpeakerNames.Add(speaker);
                Add(speaker, 50);
            }
        }

        foreach (Match match in Regex.Matches(source, @"\b\p{Lu}[\p{L}'’-]{2,}\b"))
        {
            Add(match.Value, 1);
        }

        IEnumerable<KeyValuePair<string, int>> eligibleNames = scores
            .Where(item => item.Value >= 2);
        if (attributedSpeakerNames.Count >= 2)
        {
            eligibleNames = eligibleNames.Where(item =>
                attributedSpeakerNames.Contains(item.Key));
        }

        var names = eligibleNames
            .OrderByDescending(item => item.Value)
            .ThenBy(item => item.Key, StringComparer.OrdinalIgnoreCase)
            .Select(item => item.Key)
            .Take(4)
            .ToList();
        return names;

        void Add(string value, int weight)
        {
            string name = value.Trim();
            if (name.Length < 3 || CharacterStopWords.Contains(name))
            {
                return;
            }

            scores[name] = scores.GetValueOrDefault(name) + weight;
        }
    }

    private static IReadOnlyList<OriginDossierScreenplayDialogueTurn> AttributeDialogue(
        IReadOnlyList<string> dialogueLines,
        IReadOnlyList<OriginDossierScreenplayCharacter> cast,
        IReadOnlyDictionary<string, string> explicitSpeakers,
        IReadOnlySet<string> selectedChapterDialogue)
    {
        var resolvedSpeakers = new string[dialogueLines.Count];
        for (int index = 0; index < dialogueLines.Count; index++)
        {
            string line = Normalize(dialogueLines[index]);
            string speaker = explicitSpeakers.GetValueOrDefault(line)
                ?? cast[index % cast.Count].Name;
            int speakerIndex = Array.FindIndex(
                cast.ToArray(),
                item => string.Equals(item.Name, speaker, StringComparison.OrdinalIgnoreCase));
            if (speakerIndex < 0)
            {
                speakerIndex = index % cast.Count;
                speaker = cast[speakerIndex].Name;
            }

            resolvedSpeakers[index] = speaker;
        }

        var turns = new List<OriginDossierScreenplayDialogueTurn>(dialogueLines.Count);
        for (int index = 0; index < dialogueLines.Count; index++)
        {
            string line = Normalize(dialogueLines[index]);
            string speaker = resolvedSpeakers[index];
            string? listener = resolvedSpeakers
                .Skip(index + 1)
                .FirstOrDefault(candidate => !string.Equals(
                    candidate,
                    speaker,
                    StringComparison.OrdinalIgnoreCase));
            listener ??= resolvedSpeakers
                .Take(index)
                .Reverse()
                .FirstOrDefault(candidate => !string.Equals(
                    candidate,
                    speaker,
                    StringComparison.OrdinalIgnoreCase));
            listener ??= cast
                .Select(character => character.Name)
                .First(candidate => !string.Equals(
                    candidate,
                    speaker,
                    StringComparison.OrdinalIgnoreCase));
            turns.Add(new(
                speaker,
                listener,
                line,
                UsesSupportingCanonDialogue: !selectedChapterDialogue.Contains(line)));
        }

        return turns;
    }

    private static string ResolveTimeOfDay(string chapter)
    {
        return ResolveFirstSceneAnchor(
            chapter,
            [
                (@"\b(?:sunrise|dawn|daybreak)\b", "continuous dawn"),
                (@"\b(?:morning|forenoon)\b", "continuous morning"),
                (@"\b(?:midday|noon)\b", "continuous midday"),
                (@"\b(?:afternoon)\b", "continuous afternoon"),
                (@"\b(?:sunset|dusk|twilight)\b", "continuous dusk"),
                (@"\b(?:evening)\b", "continuous evening"),
                (@"\b(?:midnight|night|moonlight)\b", "continuous night")
            ],
            "continuous overcast daytime");
    }

    private static string ResolveWeather(string chapter)
    {
        return ResolveFirstSceneAnchor(
            chapter,
            [
                (@"\b(?:rain|rainfall|drizzle|downpour)\b", "the same continuous rain"),
                (@"\b(?:snow|snowfall|blizzard)\b", "the same continuous snowfall"),
                (@"\b(?:fog|mist)\b", "the same continuous fog"),
                (@"\b(?:storm|thunder|lightning)\b", "the same continuous storm"),
                (@"\b(?:sunny|sunlight|clear sky)\b", "the same clear weather")
            ],
            "unchanged neutral weather");
    }

    private static string ResolveFirstSceneAnchor(
        string chapter,
        IReadOnlyList<(string Pattern, string Value)> candidates,
        string fallback)
    {
        (int Index, int CandidateIndex, string Value)? first = null;
        for (int candidateIndex = 0; candidateIndex < candidates.Count; candidateIndex++)
        {
            (string pattern, string value) = candidates[candidateIndex];
            Match match = Regex.Match(
                chapter,
                pattern,
                RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            if (!match.Success)
            {
                continue;
            }

            if (first is null
                || match.Index < first.Value.Index
                || match.Index == first.Value.Index && candidateIndex < first.Value.CandidateIndex)
            {
                first = (match.Index, candidateIndex, value);
            }
        }

        return first?.Value ?? fallback;
    }

    private static string ResolveLocation(OriginDossierMediaDispatchRequest request)
        => $"the same connected physical location established by “{request.SelectionLabel}”";

    internal static string ExtractSelectedChapter(
        string manuscript,
        OriginDossierMediaDispatchRequest request)
    {
        Match chapterNumber = Regex.Match(
            $"{request.SelectionId} {request.SelectionLabel}",
            @"chapter[-_\s]*0*(?<number>\d+)",
            RegexOptions.IgnoreCase);
        MatchCollection headings = Regex.Matches(
            manuscript,
            @"(?im)^#{1,6}\s*(?:chapter|kapitel)\s*0*(?<number>\d+)\b[^\r\n]*");
        Match? selectedHeading = chapterNumber.Success
            ? headings.Cast<Match>().FirstOrDefault(candidate =>
                int.TryParse(candidate.Groups["number"].Value, out int candidateNumber)
                && int.TryParse(chapterNumber.Groups["number"].Value, out int selectedNumber)
                && candidateNumber == selectedNumber)
            : null;
        if (selectedHeading is null)
        {
            string title = request.SelectionLabel
                .Split(['—', '-', ':'], 2, StringSplitOptions.TrimEntries)
                .LastOrDefault() ?? string.Empty;
            if (!string.IsNullOrWhiteSpace(title))
            {
                selectedHeading = Regex.Matches(manuscript, @"(?im)^#{1,6}\s*[^\r\n]+")
                    .Cast<Match>()
                    .FirstOrDefault(candidate =>
                        candidate.Value.Contains(title, StringComparison.OrdinalIgnoreCase));
            }
        }

        if (selectedHeading is null)
        {
            throw new InvalidOperationException("origin_dossier_media_selected_chapter_missing");
        }

        Match? nextHeading = headings.Cast<Match>()
            .FirstOrDefault(candidate => candidate.Index > selectedHeading.Index);
        int end = nextHeading?.Index ?? manuscript.Length;
        string chapter = manuscript[selectedHeading.Index..end].Trim();
        if (chapter.Length < 100)
        {
            throw new InvalidOperationException("origin_dossier_media_selected_chapter_too_short");
        }

        return chapter;
    }

    internal static IReadOnlyList<string> ExtractDialogueTurns(string chapter)
    {
        var turns = new List<string>();
        foreach (Match match in Regex.Matches(
                     chapter,
                     "[“\\\"](?<line>[^”\\\"\\r\\n]{3,240})[”\\\"]"))
        {
            Add(match.Groups["line"].Value);
        }

        foreach (Match match in Regex.Matches(
                     chapter,
                     @"(?im)^\s*(?!(?:chapter|kapitel)\b)(?:—|-|[\p{L}][\p{L}\p{N} _'’-]{1,30}:)\s*(?<line>[^\r\n]{3,240})$"))
        {
            Add(match.Groups["line"].Value);
        }

        return turns;

        void Add(string value)
        {
            string normalized = NormalizeDialogue(value);
            if (normalized.Length >= 3
                && !turns.Contains(normalized, StringComparer.OrdinalIgnoreCase))
            {
                turns.Add(normalized);
            }
        }
    }

    internal static IReadOnlyList<string> ExtractSupportingDialogueTurns(
        string manuscript,
        OriginDossierMediaDispatchRequest request)
    {
        IReadOnlyDictionary<string, string> explicitSpeakers =
            ExtractExplicitSpeakerAttributions(manuscript);
        string focusSource = $"{request.SelectionLabel} {request.SelectionSummary}";
        HashSet<string> focusTokens = Regex.Matches(
                focusSource,
                @"\b\p{Lu}[\p{L}'’-]{2,}\b")
            .Select(match => Regex.Replace(
                match.Value,
                @"(?:['’]s)$",
                string.Empty,
                RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
            .Where(token => !SupportingDialogueStopWords.Contains(token))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        HashSet<string> focusSpeakers = explicitSpeakers.Values
            .Where(focusTokens.Contains)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (focusSpeakers.Count < 2)
        {
            return Array.Empty<string>();
        }

        var candidates = new List<(int Chapter, int Score, int Index, string Text, string Speaker)>();
        var chapterFocusScores = new Dictionary<int, int>();
        int chapterIndex = 0;
        int lineIndex = 0;
        foreach (string line in Regex.Split(manuscript, @"\r?\n"))
        {
            if (Regex.IsMatch(
                    line,
                    @"^\s*#{1,6}\s*(?:chapter|kapitel)\s+\d+\b",
                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
            {
                chapterIndex++;
            }

            int speakerScore = focusSpeakers.Count(token =>
                line.Contains(token, StringComparison.OrdinalIgnoreCase));
            int contextScore = focusTokens.Count(token =>
                !focusSpeakers.Contains(token)
                && line.Contains(token, StringComparison.OrdinalIgnoreCase));
            int score = speakerScore * 5 + contextScore;
            chapterFocusScores[chapterIndex] = chapterFocusScores.GetValueOrDefault(chapterIndex) + score;
            foreach (string extractedDialogue in ExtractDialogueTurns(line))
            {
                string normalized = NormalizeDialogue(extractedDialogue);
                if (normalized.Length >= 3
                    && explicitSpeakers.TryGetValue(normalized, out string? speaker)
                    && focusSpeakers.Contains(speaker))
                {
                    candidates.Add((chapterIndex, score, lineIndex, normalized, speaker));
                }
            }

            lineIndex++;
        }

        int maximumTurns = Math.Max(request.MinimumDialogueTurns, 8);
        var coherentWindows = new List<(
            int ChapterScore,
            int AlternationScore,
            int SpeakerBalance,
            int ContentScore,
            int DialogueScore,
            int Span,
            int Start,
            IReadOnlyList<(int Chapter, int Score, int Index, string Text, string Speaker)> Turns)>();
        foreach (IGrouping<int, (int Chapter, int Score, int Index, string Text, string Speaker)> chapterGroup
                 in candidates.GroupBy(candidate => candidate.Chapter))
        {
            var ordered = chapterGroup
                .OrderBy(candidate => candidate.Index)
                .ToArray();
            for (int start = 0; start < ordered.Length; start++)
            {
                int available = Math.Min(maximumTurns, ordered.Length - start);
                if (available < request.MinimumDialogueTurns)
                {
                    break;
                }

                var window = ordered
                    .Skip(start)
                    .Take(available)
                    .ToArray();
                if (window
                    .Select(candidate => candidate.Speaker)
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Count() < 2)
                {
                    continue;
                }

                int alternationScore = window
                    .Zip(window.Skip(1), (current, next) =>
                        string.Equals(
                            current.Speaker,
                            next.Speaker,
                            StringComparison.OrdinalIgnoreCase)
                            ? 0
                            : 1)
                    .Sum();
                int speakerBalance = window
                    .GroupBy(candidate => candidate.Speaker, StringComparer.OrdinalIgnoreCase)
                    .Select(group => group.Count())
                    .Min();
                int contentScore = window.Sum(candidate =>
                {
                    int wordCount = Regex.Matches(candidate.Text, @"\b[\p{L}\p{N}'’-]+\b").Count;
                    return Math.Min(wordCount, 14) - (wordCount < 3 ? 6 : 0);
                });
                coherentWindows.Add((
                    chapterFocusScores.GetValueOrDefault(chapterGroup.Key),
                    alternationScore,
                    speakerBalance,
                    contentScore,
                    window.Sum(candidate => candidate.Score),
                    window[^1].Index - window[0].Index,
                    window[0].Index,
                    window));
            }
        }

        return coherentWindows
            .OrderByDescending(window => window.ChapterScore)
            .ThenByDescending(window => window.AlternationScore)
            .ThenByDescending(window => window.SpeakerBalance)
            .ThenByDescending(window => window.ContentScore)
            .ThenByDescending(window => window.DialogueScore)
            .ThenBy(window => window.Span)
            .ThenBy(window => window.Start)
            .Select(window => window.Turns
                .Select(candidate => candidate.Text)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray())
            .FirstOrDefault()
            ?? Array.Empty<string>();
    }

    private static IReadOnlyDictionary<string, string> ExtractExplicitSpeakerAttributions(
        string source)
    {
        var speakers = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        AddMatches(
            @"[“""](?<line>[^”""\r\n]{3,240})[”""]\s*,?\s*(?<speaker>\p{Lu}[\p{L}'’-]{2,})\s+(?i:said|says|asked|asks|answered|answers|replied|replies|whispered|whispers|shouted|shouts|called|calls|muttered|mutters|warned|warns|told|tells|exclaimed|exclaims|yelled|yells|screamed|screams|snapped|snaps|insisted|insists|ordered|orders|added|adds)\b");
        AddMatches(
            @"(?<speaker>\p{Lu}[\p{L}'’-]{2,})\s+(?i:said|says|asked|asks|answered|answers|replied|replies|whispered|whispers|shouted|shouts|called|calls|muttered|mutters|warned|warns|told|tells|exclaimed|exclaims|yelled|yells|screamed|screams|snapped|snaps|insisted|insists|ordered|orders|added|adds)\s*,?\s*[“""](?<line>[^”""\r\n]{3,240})[”""]");
        AddMatches(
            @"(?m)^\s*(?<speaker>\p{Lu}[\p{L}'’-]{2,})\s*:\s*(?<line>[^\r\n]{3,240})$");
        return speakers;

        void AddMatches(string pattern)
        {
            foreach (Match match in Regex.Matches(
                         source,
                         pattern,
                         RegexOptions.CultureInvariant))
            {
                string speaker = match.Groups["speaker"].Value.Trim();
                string line = NormalizeDialogue(match.Groups["line"].Value);
                if (!CharacterStopWords.Contains(speaker))
                {
                    speakers[line] = speaker;
                }
            }
        }
    }

    private static IReadOnlyList<string> SelectDialogueForScreenplay(
        IReadOnlyList<string> dialogueLines,
        int minimumDialogueTurns,
        int plannedShotCount)
    {
        int maximumDialogueTurns = Math.Max(
            minimumDialogueTurns,
            Math.Min(plannedShotCount - 2, 8));
        IReadOnlyList<string> eligible = dialogueLines
            .Select(NormalizeDialogue)
            .Where(OriginDossierScreenplayContract.IsDialogueTurnRenderable)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (eligible.Count < minimumDialogueTurns)
        {
            throw new InvalidOperationException("origin_dossier_media_chapter_dialogue_too_long");
        }

        if (eligible.Count <= maximumDialogueTurns)
        {
            return eligible;
        }

        var selected = new List<string>(maximumDialogueTurns);
        for (int index = 0; index < maximumDialogueTurns; index++)
        {
            int sourceIndex = (int)Math.Floor(
                index * (eligible.Count - 1d) / Math.Max(maximumDialogueTurns - 1, 1));
            selected.Add(eligible[sourceIndex]);
        }

        return selected;
    }

    private static IReadOnlyList<string> ExtractNarrativeBeats(string chapter)
    {
        string[] paragraphs = Regex.Split(chapter, @"\r?\n\s*\r?\n");
        return paragraphs
            .Select(StripDialogueFromNarrativeBeat)
            .Select(Normalize)
            .Where(paragraph => paragraph.Length >= 40)
            .Select(CompactNarrativeBeat)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string StripDialogueFromNarrativeBeat(string paragraph)
    {
        string prose = Regex.Replace(
            paragraph,
            @"(?m)^\s*#{1,6}\s*[^\r\n]*$",
            string.Empty);
        prose = Regex.Replace(
            prose,
            @"(?im)^\s*(?:—|-|[\p{L}][\p{L}\p{N} _'’-]{1,30}:)\s*[^\r\n]+$",
            string.Empty);
        prose = Regex.Replace(
            prose,
            "[“\\\"](?<line>[^”\\\"\\r\\n]{3,240})[”\\\"]",
            string.Empty);
        prose = Regex.Replace(
            prose,
            @"\b\p{Lu}[\p{L}'’-]{2,}\s+(?i:said|says|asked|asks|answered|answers|replied|replies|whispered|whispers|shouted|shouts|called|calls|muttered|mutters|warned|warns|told|tells|exclaimed|exclaims|yelled|yells|screamed|screams|snapped|snaps|insisted|insists|ordered|orders|added|adds)\b\s*[,.;:!?-]*",
            string.Empty);
        return prose;
    }

    private static string CompactNarrativeBeat(string beat)
    {
        const int preferredMaximumCharacters = 280;
        int maximum = Math.Min(
            preferredMaximumCharacters,
            OriginDossierScreenplayContract.MaximumNarrativeBeatCharacters);
        if (beat.Length <= maximum)
        {
            return beat;
        }

        string window = beat[..maximum];
        int sentenceEnd = window.LastIndexOfAny(['.', '!', '?']);
        int wordEnd = window.LastIndexOf(' ');
        int cut = sentenceEnd >= maximum / 2
            ? sentenceEnd + 1
            : wordEnd >= maximum / 2
                ? wordEnd
                : maximum;
        return window[..cut].TrimEnd() + "…";
    }

    private static string Normalize(string value)
        => Regex.Replace(value, @"\s+", " ").Trim();

    private static string NormalizeDialogue(string value)
    {
        string normalized = Normalize(value).TrimEnd(',', ';', ':', '—', '-');
        return normalized.Length > 0
            && normalized[^1] is not '.' and not '!' and not '?'
                ? normalized + "."
                : normalized;
    }

}
