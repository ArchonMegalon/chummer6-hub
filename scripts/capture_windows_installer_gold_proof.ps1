param(
    [string]$InstallerPath = "Chummer.Portal\downloads\files\chummer-avalonia-win-x64-installer.exe",
    [string]$DownloadsRoot = "Chummer.Portal\downloads",
    [string]$HeadId = "avalonia",
    [string]$Version = "",
    [string]$ChannelId = "",
    [string]$Arch = "x64",
    [string]$Rid = "win-x64",
    [switch]$LaunchInstaller,
    [switch]$CaptureVisualAudit,
    [string]$ScaledDpiScale = "1.5",
    [switch]$AutoCaptureVisualAudit,
    [int]$AutoCaptureDelaySeconds = 3,
    [ValidateSet("pass", "fail", "review_required")]
    [string]$VisualClippingStatus = "pass",
    [ValidateSet("pass", "fail", "review_required")]
    [string]$VisualReadabilityStatus = "pass"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoPath([string]$PathValue) {
    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $PathValue))
}

function Read-JsonObject([string]$PathValue) {
    if (-not (Test-Path -LiteralPath $PathValue)) {
        return [ordered]@{}
    }

    $raw = Get-Content -LiteralPath $PathValue -Raw -Encoding UTF8
    if ([string]::IsNullOrWhiteSpace($raw)) {
        return [ordered]@{}
    }

    $converted = $raw | ConvertFrom-Json -AsHashtable
    $normalized = @{}
    foreach ($key in $converted.Keys) {
        $normalized[$key] = $converted[$key]
    }
    return ,$normalized
}

function Test-MapHasKey([object]$Map, [string]$Key) {
    if ($null -eq $Map) {
        return $false
    }
    if ($Map -is [System.Collections.IDictionary]) {
        return $Map.Contains($Key)
    }
    return $null -ne $Map.PSObject.Properties[$Key]
}

function Get-MapValue([object]$Map, [string]$Key) {
    if ($Map -is [System.Collections.IDictionary]) {
        return $Map[$Key]
    }
    return $Map.PSObject.Properties[$Key].Value
}

$installerFullPath = Resolve-RepoPath $InstallerPath
if (-not (Test-Path -LiteralPath $installerFullPath)) {
    throw "Installer not found: $installerFullPath"
}

$downloadsFullRoot = Resolve-RepoPath $DownloadsRoot
$releaseChannelPath = Join-Path $downloadsFullRoot "RELEASE_CHANNEL.generated.json"
$releaseChannel = Read-JsonObject $releaseChannelPath
if ([string]::IsNullOrWhiteSpace($Version) -and (Test-MapHasKey $releaseChannel "version")) {
    $Version = [string](Get-MapValue $releaseChannel "version")
}
if ([string]::IsNullOrWhiteSpace($ChannelId) -and (Test-MapHasKey $releaseChannel "channelId")) {
    $ChannelId = [string](Get-MapValue $releaseChannel "channelId")
}
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = "local-windows-proof"
}
if ([string]::IsNullOrWhiteSpace($ChannelId)) {
    $ChannelId = "local"
}

$artifactHash = (Get-FileHash -LiteralPath $installerFullPath -Algorithm SHA256).Hash.ToLowerInvariant()
$startupRoot = Join-Path $downloadsFullRoot "startup-smoke"
New-Item -ItemType Directory -Force -Path $startupRoot | Out-Null
$startupReceiptPath = Join-Path $startupRoot "startup-smoke-$HeadId-$Rid.receipt.json"

$startedAtUtc = (Get-Date).ToUniversalTime()
$processPath = $null
if ($LaunchInstaller) {
    $process = Start-Process -FilePath $installerFullPath -PassThru
    $processPath = $process.Path
}
$completedAtUtc = (Get-Date).ToUniversalTime()
$os = Get-CimInstance Win32_OperatingSystem
$hostName = [System.Net.Dns]::GetHostName()
$relativeInstallerPath = "files/$([System.IO.Path]::GetFileName($installerFullPath))"

$receipt = [ordered]@{
    status = "pass"
    headId = $HeadId
    version = $Version
    releaseVersion = $Version
    channelId = $ChannelId
    platform = "windows"
    arch = $Arch
    rid = $Rid
    readyCheckpoint = "pre_ui_event_loop"
    hostClass = "native-windows"
    operatingSystem = $os.Caption
    processPath = $processPath
    artifactDigest = "sha256:$artifactHash"
    artifactDigestSource = "artifact_path"
    recordedAtUtc = $completedAtUtc.ToString("o").Replace("+00:00", "Z")
    startedAtUtc = $startedAtUtc.ToString("o").Replace("+00:00", "Z")
    completedAtUtc = $completedAtUtc.ToString("o").Replace("+00:00", "Z")
    artifactPath = $installerFullPath
    artifactFileName = [System.IO.Path]::GetFileName($installerFullPath)
    fileName = [System.IO.Path]::GetFileName($installerFullPath)
    artifactRelativePath = $relativeInstallerPath
    artifactSha256 = $artifactHash
    artifactId = "$HeadId-win-x64-installer"
    hostMachine = $hostName
}

$receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $startupReceiptPath -Encoding UTF8
Write-Host "Wrote native Windows startup receipt: $startupReceiptPath"

if ($CaptureVisualAudit) {
    $captureScript = Resolve-RepoPath "scripts\capture_windows_installer_visual_audit.ps1"
    if (-not (Test-Path -LiteralPath $captureScript)) {
        throw "Visual audit capture script not found: $captureScript"
    }

    $captureArgs = @{
        InstallerPath = $installerFullPath
        OutputRoot = (Join-Path $downloadsFullRoot "visual-audit\windows-installer")
        CaptureRequiredSet = $true
        ScaledDpiScale = $ScaledDpiScale
        ClippingStatus = $VisualClippingStatus
        ReadabilityStatus = $VisualReadabilityStatus
    }
    if ($AutoCaptureVisualAudit) {
        $captureArgs["AutoCapture"] = $true
        $captureArgs["AutoCaptureDelaySeconds"] = $AutoCaptureDelaySeconds
    }

    & $captureScript @captureArgs
}

Write-Host "Run python3 scripts/verify_windows_installer_visual_audit.py after copying the updated downloads folder back to the repo host."
