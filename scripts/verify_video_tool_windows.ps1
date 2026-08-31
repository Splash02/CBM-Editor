param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,
    [ValidateSet("windows-x64", "linux-x86_64")]
    [string]$Platform = "windows-x64"
)

$ErrorActionPreference = "Stop"
$resolved = [System.IO.Path]::GetFullPath($Artifact)
if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
    throw "Artifact not found: $resolved"
}
if ($Platform -eq "linux-x86_64") {
    $stream = [System.IO.File]::OpenRead($resolved)
    try {
        $header = New-Object byte[] 20
        if ($stream.Read($header, 0, $header.Length) -ne $header.Length) {
            throw "Linux artifact is too small."
        }
    } finally {
        $stream.Dispose()
    }
    if ($header[0] -ne 0x7f -or $header[1] -ne 0x45 -or $header[2] -ne 0x4c -or $header[3] -ne 0x46 -or
        $header[4] -ne 2 -or $header[5] -ne 1 -or [BitConverter]::ToUInt16($header, 18) -ne 62) {
        throw "Linux artifact is not a little-endian x86-64 ELF executable."
    }
}
$platformRoot = "C:\ProgramData\Microsoft\Windows Defender\Platform"
$mpCmdRun = $null
if (Test-Path -LiteralPath $platformRoot -PathType Container) {
    $mpCmdRun = Get-ChildItem -LiteralPath $platformRoot -Directory |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName "MpCmdRun.exe" } |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
if (-not $mpCmdRun) {
    $fallback = "C:\Program Files\Windows Defender\MpCmdRun.exe"
    if (Test-Path -LiteralPath $fallback -PathType Leaf) {
        $mpCmdRun = $fallback
    }
}
if (-not $mpCmdRun) {
    throw "Microsoft Defender command-line scanner was not found."
}
& $mpCmdRun -Scan -ScanType 3 -File $resolved -DisableRemediation
if ($LASTEXITCODE -ne 0) {
    throw "Microsoft Defender reported a detection or scan error."
}
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$manifestPath = Join-Path $projectRoot "cbm_editor\vendor\video\manifest.json"
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$entry = $manifest.artifacts.$Platform
$entry.sha256 = (Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
$entry.size = (Get-Item -LiteralPath $resolved).Length
$signatureVersion = try { (Get-MpComputerStatus).AntivirusSignatureVersion } catch { "" }
$entry.scan = if ($signatureVersion) { "Microsoft Defender $signatureVersion" } else { "Microsoft Defender" }
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $manifestPath -Encoding utf8
