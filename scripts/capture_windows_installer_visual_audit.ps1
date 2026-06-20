param(
    [string]$InstallerPath = "Chummer.Portal\downloads\files\chummer-avalonia-win-x64-installer.exe",
    [string]$OutputRoot = "Chummer.Portal\downloads\visual-audit\windows-installer",
    [string]$DpiScale = "1.0",
    [ValidateSet("install-progress", "completion")]
    [string]$Surface = "completion",
    [ValidateSet("pass", "fail", "review_required")]
    [string]$ClippingStatus = "review_required",
    [ValidateSet("pass", "fail", "review_required")]
    [string]$ReadabilityStatus = "review_required",
    [switch]$LaunchInstaller,
    [switch]$CaptureRequiredSet,
    [string]$ScaledDpiScale = "1.5",
    [switch]$AutoCapture,
    [int]$AutoCaptureDelaySeconds = 3
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

    return $raw | ConvertFrom-Json -AsHashtable
}

function Test-IsDefaultDpi([object]$Value) {
    $text = [string]$Value
    return $text -in @("1", "1.0", "100", "100%")
}

function Normalize-Surface([object]$Value) {
    $text = ([string]$Value).Trim().ToLowerInvariant().Replace("_", "-").Replace(" ", "-")
    switch ($text) {
        "progress" { return "install-progress" }
        "install" { return "install-progress" }
        "splash" { return "install-progress" }
        "install-splash" { return "install-progress" }
        "complete" { return "completion" }
        "install-complete" { return "completion" }
        default { return $text }
    }
}

$installerFullPath = Resolve-RepoPath $InstallerPath
if (-not (Test-Path -LiteralPath $installerFullPath)) {
    throw "Installer not found: $installerFullPath"
}

$outputFullRoot = Resolve-RepoPath $OutputRoot
New-Item -ItemType Directory -Force -Path $outputFullRoot | Out-Null
$sourcePath = Join-Path $outputFullRoot "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"

if ($LaunchInstaller) {
    Start-Process -FilePath $installerFullPath | Out-Null
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$captureRequests = @()
if ($CaptureRequiredSet) {
    $captureRequests = @(
        [ordered]@{ Surface = "install-progress"; DpiScale = "1.0" },
        [ordered]@{ Surface = "completion"; DpiScale = "1.0" },
        [ordered]@{ Surface = "install-progress"; DpiScale = $ScaledDpiScale },
        [ordered]@{ Surface = "completion"; DpiScale = $ScaledDpiScale }
    )
}
else {
    $captureRequests = @([ordered]@{ Surface = $Surface; DpiScale = $DpiScale })
}

$newRows = @()
foreach ($request in $captureRequests) {
    $captureSurface = [string]$request.Surface
    $captureDpiScale = [string]$request.DpiScale
    Write-Host "Put the Windows installer surface to audit on screen, then press Enter."
    Write-Host "Surface: $captureSurface; DPI label: $captureDpiScale; clipping=$ClippingStatus; readability=$ReadabilityStatus"
    if ($AutoCapture) {
        Write-Host "Auto-capturing in $AutoCaptureDelaySeconds seconds."
        Start-Sleep -Seconds $AutoCaptureDelaySeconds
    }
    else {
        [void](Read-Host)
    }

    $bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $graphics.CopyFromScreen($bounds.Left, $bounds.Top, 0, 0, $bounds.Size)
        $safeSurface = ($captureSurface -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
        if ([string]::IsNullOrWhiteSpace($safeSurface)) {
            $safeSurface = "installer"
        }
        $safeDpiScale = ($captureDpiScale -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
        $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
        $screenshotName = "windows-installer-$safeSurface-dpi-$safeDpiScale-$stamp.png"
        $screenshotPath = Join-Path $outputFullRoot $screenshotName
        $bitmap.Save($screenshotPath, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }

    $relativeScreenshotPath = Split-Path -Leaf $screenshotPath
    $newRows += [ordered]@{
        path = $relativeScreenshotPath
        dpiScale = $captureDpiScale
        surface = $captureSurface
        clippingStatus = $ClippingStatus
        readabilityStatus = $ReadabilityStatus
        hostClass = "native-windows"
        capturedAtUtc = (Get-Date).ToUniversalTime().ToString("o").Replace("+00:00", "Z")
    }
    Write-Host "Captured screenshot: $screenshotPath"
}

$artifactSha = (Get-FileHash -LiteralPath $installerFullPath -Algorithm SHA256).Hash.ToLowerInvariant()
$os = Get-CimInstance Win32_OperatingSystem
$source = Read-JsonObject $sourcePath
$existingScreenshots = @()
if ($source.ContainsKey("screenshots") -and $null -ne $source["screenshots"]) {
    $existingScreenshots = @($source["screenshots"])
}

$screenshots = @($existingScreenshots + $newRows)
$allPass = $true
$hasDefaultDpi = $false
$hasScaledDpi = $false
$requiredSurfaces = @("install-progress", "completion")
$surfaceCoverage = @{}
foreach ($requiredSurface in $requiredSurfaces) {
    $surfaceCoverage[$requiredSurface] = @{
        defaultDpi = $false
        scaledDpi = $false
    }
}
foreach ($item in $screenshots) {
    if (([string]$item.clippingStatus).ToLowerInvariant() -ne "pass") {
        $allPass = $false
    }
    if (([string]$item.readabilityStatus).ToLowerInvariant() -ne "pass") {
        $allPass = $false
    }
    if (Test-IsDefaultDpi $item.dpiScale) {
        $hasDefaultDpi = $true
        $surfaceName = Normalize-Surface $item.surface
        if ($surfaceCoverage.ContainsKey($surfaceName)) {
            $surfaceCoverage[$surfaceName].defaultDpi = $true
        }
    }
    else {
        $hasScaledDpi = $true
        $surfaceName = Normalize-Surface $item.surface
        if ($surfaceCoverage.ContainsKey($surfaceName)) {
            $surfaceCoverage[$surfaceName].scaledDpi = $true
        }
    }
}
$hasRequiredSurfaceCoverage = $true
foreach ($requiredSurface in $requiredSurfaces) {
    if (-not $surfaceCoverage[$requiredSurface].defaultDpi -or -not $surfaceCoverage[$requiredSurface].scaledDpi) {
        $hasRequiredSurfaceCoverage = $false
    }
}

$status = "fail"
if ($allPass -and $hasDefaultDpi -and $hasScaledDpi -and $hasRequiredSurfaceCoverage) {
    $status = "pass"
}
elseif (-not $allPass -or -not $hasRequiredSurfaceCoverage) {
    $status = "review_required"
}

$payload = [ordered]@{
    contract_name = "chummer.windows_installer_visual_audit.source"
    status = $status
    platform = "windows"
    hostClass = "native-windows-$($os.Caption)"
    artifactPath = $installerFullPath
    artifactSha256 = $artifactSha
    sourceUpdatedAtUtc = (Get-Date).ToUniversalTime().ToString("o").Replace("+00:00", "Z")
    requiredSurfaces = $requiredSurfaces
    surfaceCoverage = $surfaceCoverage
    screenshots = $screenshots
}

$payload | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $sourcePath -Encoding UTF8
Write-Host "Updated source receipt: $sourcePath"
Write-Host "Status: $status"
