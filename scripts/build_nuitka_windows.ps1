param(
    [string]$PythonExe = "python",
    [ValidateSet("Preview", "Release", "Both")]
    [string]$Edition = "Both",
    [switch]$NoCompression,
    [switch]$Standalone,
    [switch]$AsArchive,
    [switch]$NoDll,
    [string]$PreviewVersion = "",
    [string]$PreviewOutputFile = "",
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $resolvedOutputRoot = Join-Path $projectRoot "build\nuitka\windows"
} elseif ([System.IO.Path]::IsPathRooted($OutputRoot)) {
    $resolvedOutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
} else {
    $resolvedOutputRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $OutputRoot))
}
$appVersion = "1.3"

function Invoke-CBMBuild {
    param(
        [string]$EntryFile,
        [string]$OutputFile,
        [string]$IconFile,
        [string]$ProductName,
        [string]$OutputDirectory
    )

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $description = "Custom Beatmaps Editor"
    $copyright = "Copyright $([char]0x00A9) 2026 Splash!"
    $buildMode = if ($Standalone) { "--mode=standalone" } else { "--onefile" }

    $nuitkaArgs = @(
        "-m",
        "nuitka",
        $buildMode,
        "--enable-plugin=pyqt6",
        "--windows-console-mode=disable",
        "--file-version=1.3.0.0",
        "--product-version=1.3.0.0",
        "--file-description=$description",
        "--copyright=$copyright",
        "--company-name=Splash!",
        "--product-name=$ProductName",
        "--windows-icon-from-ico=$IconFile",
        "--include-data-dir=cbm_editor/sounds=cbm_editor/sounds",
        "--include-data-file=cbm_editor/vendor/bass/manifest.json=cbm_editor/vendor/bass/manifest.json",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE.txt=cbm_editor/vendor/bass/LICENSE.txt",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE_BASSALAC.txt=cbm_editor/vendor/bass/LICENSE_BASSALAC.txt",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE_BASSENC.txt=cbm_editor/vendor/bass/LICENSE_BASSENC.txt",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE_BASSENC_MP3.txt=cbm_editor/vendor/bass/LICENSE_BASSENC_MP3.txt",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE_BASSFLAC.txt=cbm_editor/vendor/bass/LICENSE_BASSFLAC.txt",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE_BASSMIX.txt=cbm_editor/vendor/bass/LICENSE_BASSMIX.txt",
        "--include-data-file=cbm_editor/vendor/bass/LICENSE_BASSOPUS.txt=cbm_editor/vendor/bass/LICENSE_BASSOPUS.txt",
        "--include-data-file=cbm_editor/vendor/bass/THIRD_PARTY_NOTICES.txt=cbm_editor/vendor/bass/THIRD_PARTY_NOTICES.txt",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bass.dll=cbm_editor/vendor/bass/win-x64/bass.dll",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bassalac.dll=cbm_editor/vendor/bass/win-x64/bassalac.dll",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bassenc.dll=cbm_editor/vendor/bass/win-x64/bassenc.dll",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bassenc_mp3.dll=cbm_editor/vendor/bass/win-x64/bassenc_mp3.dll",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bassflac.dll=cbm_editor/vendor/bass/win-x64/bassflac.dll",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bassmix.dll=cbm_editor/vendor/bass/win-x64/bassmix.dll",
        "--include-data-file=cbm_editor/vendor/bass/win-x64/bassopus.dll=cbm_editor/vendor/bass/win-x64/bassopus.dll",
        "--output-dir=$OutputDirectory",
        "--output-filename=$OutputFile",
        $EntryFile
    )

    if ($NoCompression -and -not $Standalone) {
        $nuitkaArgs = @("-m", "nuitka", "--onefile-no-compression") + $nuitkaArgs[2..($nuitkaArgs.Length - 1)]
    }
    if ($AsArchive -and -not $Standalone) {
        $nuitkaArgs = @("-m", "nuitka", "--onefile-as-archive") + $nuitkaArgs[2..($nuitkaArgs.Length - 1)]
    }
    if ($NoDll -and -not $Standalone) {
        $nuitkaArgs = @("-m", "nuitka", "--onefile-no-dll") + $nuitkaArgs[2..($nuitkaArgs.Length - 1)]
    }

    Push-Location $projectRoot
    try {
        & $PythonExe @nuitkaArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }
}

if ($Edition -in @("Preview", "Both")) {
    if ([string]::IsNullOrWhiteSpace($PreviewOutputFile)) {
        if ([string]::IsNullOrWhiteSpace($PreviewVersion)) {
            throw "PreviewVersion is required for preview builds."
        }
        $PreviewOutputFile = "CBM_Editor_V${appVersion}_PREVIEW${PreviewVersion}.exe"
    }
    Invoke-CBMBuild "scripts\CBM_Editor_preview.py" $PreviewOutputFile "scripts\icon_pre.ico" "CBM Editor -PREVIEW-" (Join-Path $resolvedOutputRoot "preview")
}

if ($Edition -in @("Release", "Both")) {
    Invoke-CBMBuild "scripts\CBM_Editor_release.py" "CBM_Editor_V${appVersion}.exe" "scripts\icon.ico" "CBM Editor" (Join-Path $resolvedOutputRoot "release")
}
