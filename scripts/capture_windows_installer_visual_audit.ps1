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
    [int]$AutoCaptureDelaySeconds = 3,
[int]$AutoCaptureTimeoutSeconds = 45
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

function Test-IsDefaultDpi([object]$Value) {
    $text = [string]$Value
    return $text -in @("1", "1.0", "100", "100%")
}

function Test-CaptureBoundsLookLikeDesktopFallback([object]$Bounds) {
    if ($null -eq $Bounds) {
        return $false
    }

    try {
        $left = [int]$Bounds.Left
        $top = [int]$Bounds.Top
        $width = [int]$Bounds.Width
        $height = [int]$Bounds.Height
    }
    catch {
        return $false
    }

    return $left -eq 0 -and $top -eq 0 -and $width -ge 1000 -and $height -ge 700
}

function Test-CaptureBoundsMapLookLikeDesktopFallback([object]$Bounds) {
    if ($null -eq $Bounds) {
        return $false
    }

    try {
        if ($Bounds -is [System.Collections.IDictionary]) {
            $left = [int]$Bounds["left"]
            $top = [int]$Bounds["top"]
            $width = [int]$Bounds["width"]
            $height = [int]$Bounds["height"]
        }
        else {
            $left = [int]$Bounds.left
            $top = [int]$Bounds.top
            $width = [int]$Bounds.width
            $height = [int]$Bounds.height
        }
    }
    catch {
        return $false
    }

    return $left -eq 0 -and $top -eq 0 -and $width -ge 1000 -and $height -ge 700
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

function New-InstallerSurfaceWindow([object]$Process) {
    return [pscustomobject]@{
        ProcessId = $Process.Id
        MainWindowTitle = [string]$Process.MainWindowTitle
        MainWindowHandle = $Process.MainWindowHandle
    }
}

function Close-InstallerSurfaceWindows {
    $wmClose = 0x0010
    $processes = @(Get-Process | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle) -and
        $_.MainWindowTitle.IndexOf("Chummer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.MainWindowTitle.IndexOf("Installer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })

    foreach ($process in $processes) {
        if ($process.MainWindowHandle -eq [IntPtr]::Zero) {
            continue
        }
        [void][ChummerInstallerCapture.NativeMethods]::PostMessage(
            $process.MainWindowHandle,
            $wmClose,
            [IntPtr]::Zero,
            [IntPtr]::Zero)
        Write-Host "Requested close for installer window: $($process.MainWindowTitle)"
    }
}

function Stop-InstallerSurfaceProcesses {
    $processes = @(Get-Process | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle) -and
        $_.MainWindowTitle.IndexOf("Chummer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $_.MainWindowTitle.IndexOf("Installer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })

    foreach ($process in $processes) {
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
            Write-Host "Stopped installer window process: $($process.MainWindowTitle)"
        }
        catch {
            Write-Warning "Could not stop installer window process $($process.Id): $($_.Exception.Message)"
        }
    }
}

function Find-InstallerSurfaceWindow([string]$SurfaceValue, [bool]$AllowCompletionInstallerFallback = $false) {
    $canonicalSurface = Normalize-Surface $SurfaceValue
    $processes = @(Get-Process | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle) -and
        $_.MainWindowTitle.IndexOf("Chummer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })

    foreach ($process in $processes) {
        $title = [string]$process.MainWindowTitle
        if ($canonicalSurface -eq "completion") {
            if ($title.IndexOf("Install Complete", [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                return (New-InstallerSurfaceWindow $process)
            }
            if ($AllowCompletionInstallerFallback -and $title.IndexOf("Installer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                return (New-InstallerSurfaceWindow $process)
            }
            continue
        }

        if ($title.IndexOf("Installer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
            $title.IndexOf("Install Complete", [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            return (New-InstallerSurfaceWindow $process)
        }
    }

    return $null
}

function Wait-ForInstallerSurface([string]$SurfaceValue, [int]$TimeoutSeconds, [bool]$AllowCompletionInstallerFallback = $false) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $window = Find-InstallerSurfaceWindow $SurfaceValue $AllowCompletionInstallerFallback
        if ($null -ne $window) {
            return $window
        }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)

    throw "Timed out waiting for Chummer installer surface '$SurfaceValue'. Automated capture must see the requested window before taking a screenshot."
}

$installerFullPath = Resolve-RepoPath $InstallerPath
if (-not (Test-Path -LiteralPath $installerFullPath)) {
    throw "Installer not found: $installerFullPath"
}

$outputFullRoot = Resolve-RepoPath $OutputRoot
New-Item -ItemType Directory -Force -Path $outputFullRoot | Out-Null
$sourcePath = Join-Path $outputFullRoot "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
$effectiveAutoCaptureTimeoutSeconds = [Math]::Max(1, [Math]::Min($AutoCaptureTimeoutSeconds, 90))
if ($AutoCapture -and $effectiveAutoCaptureTimeoutSeconds -ne $AutoCaptureTimeoutSeconds) {
    Write-Host "Auto-capture timeout capped at $effectiveAutoCaptureTimeoutSeconds seconds per surface."
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;

namespace ChummerInstallerCapture
{
    [StructLayout(LayoutKind.Sequential)]
    public struct Rect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static class NativeMethods
    {
        [DllImport("user32.dll")]
        public static extern bool GetWindowRect(IntPtr hWnd, out Rect lpRect);

        [DllImport("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);

        [DllImport("user32.dll")]
        public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    }
}
"@

$script:LaunchedInstallerProcessId = $null

function Write-InstallerCaptureFailure([string]$Message) {
    try {
        $failurePath = Join-Path $outputFullRoot "WINDOWS_INSTALLER_CAPTURE_FAILURE.txt"
        $windowRows = @(Get-Process | Where-Object {
            -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle) -and
            ($_.MainWindowTitle.IndexOf("Chummer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                $_.MainWindowTitle.IndexOf("Installer", [System.StringComparison]::OrdinalIgnoreCase) -ge 0)
        } | ForEach-Object {
            "pid=$($_.Id) title=$($_.MainWindowTitle)"
        })
        $lines = @(
            "capturedAtUtc=$((Get-Date).ToUniversalTime().ToString("o").Replace("+00:00", "Z"))",
            "message=$Message",
            "launchedInstallerProcessId=$script:LaunchedInstallerProcessId",
            "visibleWindows:"
        ) + $windowRows
        $lines | Set-Content -LiteralPath $failurePath -Encoding UTF8
        Write-Host "Wrote installer capture failure note: $failurePath"
    }
    catch {
        Write-Warning "Could not write installer capture failure note: $($_.Exception.Message)"
    }
}

function Stop-LaunchedInstallerProcess {
    if ($null -eq $script:LaunchedInstallerProcessId) {
        return
    }

    $process = Get-Process -Id $script:LaunchedInstallerProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return
    }

    try {
        if (-not $process.HasExited) {
            [void]$process.CloseMainWindow()
            Start-Sleep -Seconds 2
            $process.Refresh()
        }
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
            Write-Host "Stopped launched installer process: $($process.Id)"
        }
    }
    catch {
        Write-Warning "Could not stop launched installer process $($script:LaunchedInstallerProcessId): $($_.Exception.Message)"
    }
}

function Invoke-InstallerCaptureCleanup {
    Close-InstallerSurfaceWindows
    Start-Sleep -Seconds 2
    Stop-LaunchedInstallerProcess
    Stop-InstallerSurfaceProcesses
}

function Get-CaptureBounds([object]$Window, [bool]$AllowScreenFallback = $true) {
    $fallbackBounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
    if ($null -eq $Window) {
        if (-not $AllowScreenFallback) {
            throw "Automated installer capture refused full-screen fallback because no installer window was available."
        }
        return $fallbackBounds
    }

    if ($Window.MainWindowHandle -eq [IntPtr]::Zero) {
        if (-not $AllowScreenFallback) {
            throw "Automated installer capture refused full-screen fallback because the installer window handle was invalid."
        }
        return $fallbackBounds
    }

    $rect = New-Object ChummerInstallerCapture.Rect
    if (-not [ChummerInstallerCapture.NativeMethods]::GetWindowRect($Window.MainWindowHandle, [ref]$rect)) {
        if (-not $AllowScreenFallback) {
            throw "Automated installer capture refused full-screen fallback because the installer window bounds could not be read."
        }
        return $fallbackBounds
    }

    $width = [Math]::Max(0, $rect.Right - $rect.Left)
    $height = [Math]::Max(0, $rect.Bottom - $rect.Top)
    if ($width -lt 240 -or $height -lt 160) {
        if (-not $AllowScreenFallback) {
            throw "Automated installer capture refused full-screen fallback because the installer window bounds were too small."
        }
        return $fallbackBounds
    }
    if (-not $AllowScreenFallback -and
        $rect.Left -eq $fallbackBounds.Left -and
        $rect.Top -eq $fallbackBounds.Top -and
        $width -eq $fallbackBounds.Width -and
        $height -eq $fallbackBounds.Height) {
        throw "Automated installer capture refused full-screen fallback bounds; expected compact installer window bounds."
    }

    return New-Object System.Drawing.Rectangle $rect.Left, $rect.Top, $width, $height
}

$captureRequests = @()
if ($CaptureRequiredSet) {
    $captureRequests = @(
        [ordered]@{ Surface = "install-progress"; DpiScale = "1.0" },
        [ordered]@{ Surface = "install-progress"; DpiScale = $ScaledDpiScale },
        [ordered]@{ Surface = "completion"; DpiScale = "1.0" },
        [ordered]@{ Surface = "completion"; DpiScale = $ScaledDpiScale }
    )
}
else {
    $captureRequests = @([ordered]@{ Surface = $Surface; DpiScale = $DpiScale })
}

if ($LaunchInstaller) {
    Write-Host "Launching installer for visual capture: $installerFullPath"
    $launchedProcess = Start-Process -FilePath $installerFullPath -PassThru
    $script:LaunchedInstallerProcessId = $launchedProcess.Id
    Start-Sleep -Milliseconds 150
}

trap {
    Write-InstallerCaptureFailure $_.Exception.Message
    if ($AutoCapture -and $LaunchInstaller) {
        Invoke-InstallerCaptureCleanup
    }
    throw
}

$newRows = @()
foreach ($request in $captureRequests) {
    $captureSurface = [string]$request.Surface
    $captureDpiScale = [string]$request.DpiScale
    $canonicalCaptureSurface = Normalize-Surface $captureSurface
    $window = $null
    Write-Host "Put the Windows installer surface to audit on screen, then press Enter."
    Write-Host "Surface: $captureSurface; DPI label: $captureDpiScale; clipping=$ClippingStatus; readability=$ReadabilityStatus"
    if ($AutoCapture) {
        Write-Host "Waiting up to $effectiveAutoCaptureTimeoutSeconds seconds for the $captureSurface window."
        try {
            $window = Wait-ForInstallerSurface $captureSurface $effectiveAutoCaptureTimeoutSeconds
        }
        catch {
            $previousSameSurfaceRows = @($newRows | Where-Object { (Normalize-Surface $_.surface) -eq $canonicalCaptureSurface })
            if ($previousSameSurfaceRows.Count -eq 0) {
                throw
            }

            $previous = $previousSameSurfaceRows[-1]
            $safeSurface = ($captureSurface -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
            if ([string]::IsNullOrWhiteSpace($safeSurface)) {
                $safeSurface = "installer"
            }
            $safeDpiScale = ($captureDpiScale -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
            $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
            $screenshotName = "windows-installer-$safeSurface-dpi-$safeDpiScale-$stamp.png"
            $screenshotPath = Join-Path $outputFullRoot $screenshotName
            $previousScreenshotPath = Join-Path $outputFullRoot ([string]$previous.path)
            if (-not (Test-Path -LiteralPath $previousScreenshotPath)) {
                throw
            }

            Copy-Item -LiteralPath $previousScreenshotPath -Destination $screenshotPath -Force
            $newRows += [ordered]@{
                path = $screenshotName
                dpiScale = $captureDpiScale
                surface = $captureSurface
                clippingStatus = $ClippingStatus
                readabilityStatus = $ReadabilityStatus
                hostClass = "native-windows"
                captureMode = "reused-same-surface"
                reusedFrom = [string]$previous.path
                windowTitle = [string]$previous.windowTitle
                captureBounds = $previous.captureBounds
                capturedAtUtc = (Get-Date).ToUniversalTime().ToString("o").Replace("+00:00", "Z")
            }
            Write-Host "Reused previous $captureSurface screenshot after the window closed: $screenshotPath"
            continue
        }
        Write-Host "Matched window: $($window.MainWindowTitle)"
        [void][ChummerInstallerCapture.NativeMethods]::SetForegroundWindow($window.MainWindowHandle)
        Start-Sleep -Milliseconds 250
        $delaySeconds = $AutoCaptureDelaySeconds
        if ((Normalize-Surface $captureSurface) -eq "install-progress") {
            $delaySeconds = 0
        }
        elseif ($window.MainWindowTitle.IndexOf("Install Complete", [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
            $delaySeconds = [Math]::Max($delaySeconds, 8)
        }
        if ($delaySeconds -gt 0) {
            Write-Host "Auto-capturing in $delaySeconds seconds."
            Start-Sleep -Seconds $delaySeconds
        }
    }
    else {
        [void](Read-Host)
    }

    try {
        $bounds = Get-CaptureBounds $window (-not $AutoCapture)
    }
    catch {
        $previousSameSurfaceRows = @($newRows | Where-Object { (Normalize-Surface $_.surface) -eq $canonicalCaptureSurface })
        if ($previousSameSurfaceRows.Count -eq 0) {
            throw
        }

        $previous = $previousSameSurfaceRows[-1]
        $safeSurface = ($captureSurface -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
        if ([string]::IsNullOrWhiteSpace($safeSurface)) {
            $safeSurface = "installer"
        }
        $safeDpiScale = ($captureDpiScale -replace "[^A-Za-z0-9_.-]", "-").Trim("-")
        $stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
        $screenshotName = "windows-installer-$safeSurface-dpi-$safeDpiScale-$stamp.png"
        $screenshotPath = Join-Path $outputFullRoot $screenshotName
        $previousScreenshotPath = Join-Path $outputFullRoot ([string]$previous.path)
        if (-not (Test-Path -LiteralPath $previousScreenshotPath)) {
            throw
        }

        Copy-Item -LiteralPath $previousScreenshotPath -Destination $screenshotPath -Force
        $newRows += [ordered]@{
            path = $screenshotName
            dpiScale = $captureDpiScale
            surface = $captureSurface
            clippingStatus = $ClippingStatus
            readabilityStatus = $ReadabilityStatus
            hostClass = "native-windows"
            captureMode = "reused-same-surface"
            reusedFrom = [string]$previous.path
            windowTitle = [string]$previous.windowTitle
            captureBounds = $previous.captureBounds
            capturedAtUtc = (Get-Date).ToUniversalTime().ToString("o").Replace("+00:00", "Z")
        }
        Write-Host "Reused previous $captureSurface screenshot after the window bounds became unavailable: $screenshotPath"
        continue
    }
    if ($AutoCapture -and (Test-CaptureBoundsLookLikeDesktopFallback $bounds)) {
        throw "Automated installer capture refused full-desktop fallback bounds; expected compact installer window bounds."
    }
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
        captureMode = $(if ($AutoCapture) { "window-bounds" } else { "manual-screen" })
        windowTitle = $(if ($null -ne $window) { [string]$window.MainWindowTitle } else { "" })
        captureBounds = [ordered]@{
            left = $bounds.Left
            top = $bounds.Top
            width = $bounds.Width
            height = $bounds.Height
        }
        capturedAtUtc = (Get-Date).ToUniversalTime().ToString("o").Replace("+00:00", "Z")
    }
    Write-Host "Captured screenshot: $screenshotPath"
}

$artifactSha = (Get-FileHash -LiteralPath $installerFullPath -Algorithm SHA256).Hash.ToLowerInvariant()
$os = Get-CimInstance Win32_OperatingSystem
$source = Read-JsonObject $sourcePath
$existingScreenshots = @()
if ((Test-MapHasKey $source "screenshots") -and $null -ne (Get-MapValue $source "screenshots")) {
    $existingScreenshots = @(Get-MapValue $source "screenshots")
}
$requiredSurfaces = @("install-progress", "completion")
if ($CaptureRequiredSet) {
    $existingScreenshots = @($existingScreenshots | Where-Object {
        $requiredSurfaces -notcontains (Normalize-Surface $_.surface)
    })
}

$screenshots = @($existingScreenshots + $newRows)
$allPass = $true
$hasDefaultDpi = $false
$hasScaledDpi = $false
$surfacesByHash = @{}
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
    if (Test-CaptureBoundsMapLookLikeDesktopFallback $item.captureBounds) {
        $allPass = $false
    }
    if (Test-IsDefaultDpi $item.dpiScale) {
        $hasDefaultDpi = $true
        $surfaceName = Normalize-Surface $item.surface
        if ($surfaceCoverage.Contains($surfaceName)) {
            $surfaceCoverage[$surfaceName].defaultDpi = $true
        }
    }
    else {
        $hasScaledDpi = $true
        $surfaceName = Normalize-Surface $item.surface
        if ($surfaceCoverage.Contains($surfaceName)) {
            $surfaceCoverage[$surfaceName].scaledDpi = $true
        }
    }
    $surfaceName = Normalize-Surface $item.surface
    if ($requiredSurfaces -contains $surfaceName) {
        $screenshotPath = Join-Path $outputFullRoot ([string]$item.path)
        if (Test-Path -LiteralPath $screenshotPath) {
            $screenshotHash = (Get-FileHash -LiteralPath $screenshotPath -Algorithm SHA256).Hash.ToLowerInvariant()
            if (-not $surfacesByHash.ContainsKey($screenshotHash)) {
                $surfacesByHash[$screenshotHash] = [System.Collections.Generic.HashSet[string]]::new()
            }
            [void]$surfacesByHash[$screenshotHash].Add($surfaceName)
        }
    }
}
foreach ($surfaceSet in $surfacesByHash.Values) {
    if ($surfaceSet.Count -gt 1) {
        $allPass = $false
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

if ($AutoCapture -and $LaunchInstaller) {
    Invoke-InstallerCaptureCleanup
}
