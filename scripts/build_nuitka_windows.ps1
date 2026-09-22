param(
    [string]$PythonExe = "python",
    [ValidateSet("Preview", "Release", "Both")]
    [string]$Edition = "Both",
    [switch]$NoCompression,
    [switch]$Standalone,
    [switch]$AsArchive,
    [switch]$NoDll,
    [switch]$MicrosoftStore,
    [string]$PreviewVersion = "",
    [string]$PreviewOutputFile = "",
    [string]$OutputRoot = "",
    [string]$StoreIdentityName = "",
    [string]$StorePublisher = "",
    [string]$StorePublisherDisplayName = "Splash!",
    [string]$StoreVersion = "",
    [string]$SigningCertificatePath = "",
    [string]$SigningCertificatePassword = ""
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
Push-Location $projectRoot
try {
    $versionInfo = (& $PythonExe -c "from cbm_editor.versioning import APP_BASE_VERSION, APP_PREVIEW_NUMBER; print(f'{APP_BASE_VERSION}|{APP_PREVIEW_NUMBER}')").Trim()
    $versionExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
if ($versionExitCode -ne 0 -or $versionInfo -notmatch '^\d+\.\d+\|\d+$') {
    throw "Could not read the application version from cbm_editor/versioning.py."
}
$versionParts = $versionInfo.Split('|')
$appVersion = $versionParts[0]
$fileVersion = "${appVersion}.0.0"
$sourcePreviewVersion = $versionParts[1]
if ([string]::IsNullOrWhiteSpace($PreviewVersion)) {
    $PreviewVersion = $sourcePreviewVersion
} elseif ($PreviewVersion -ne $sourcePreviewVersion) {
    throw "PreviewVersion $PreviewVersion does not match the source version $sourcePreviewVersion."
}
if ($MicrosoftStore) {
    if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
        throw "Microsoft Store builds are only available on Windows."
    }
    if ($Edition -eq "Both") {
        throw "Microsoft Store builds require either -Edition Release or -Edition Preview. Build the two Store products separately."
    }
    if ([string]::IsNullOrWhiteSpace($StoreIdentityName)) {
        throw "StoreIdentityName is required for Microsoft Store builds. Copy it from Partner Center product identity details."
    }
    if ([string]::IsNullOrWhiteSpace($StorePublisher)) {
        throw "StorePublisher is required for Microsoft Store builds. Copy it from Partner Center product identity details."
    }
    if ([string]::IsNullOrWhiteSpace($StoreVersion)) {
        $appVersionParts = $appVersion.Split('.')
        $fraction = $appVersionParts[1]
        $storeMajor = [int64]("$($appVersionParts[0])$($fraction.Substring(0, 1))")
        $storeMinor = if ($fraction.Length -gt 1) { [int64]$fraction.Substring(1) } else { 0 }
        $storeBuild = if ($Edition -eq "Preview") { [int64]$PreviewVersion } else { 0 }
        $StoreVersion = "$storeMajor.$storeMinor.$storeBuild.0"
    }
    $storeVersionParts = $StoreVersion.Split('.')
    $invalidStoreVersionParts = @($storeVersionParts | Where-Object { $_ -notmatch '^(0|[1-9]\d*)$' })
    if ($storeVersionParts.Count -ne 4 -or $invalidStoreVersionParts.Count -gt 0) {
        throw "StoreVersion must contain four numeric parts, for example 2.0.1.0."
    }
    $storeVersionNumbers = @($storeVersionParts | ForEach-Object { [int64]$_ })
    if ($storeVersionNumbers[0] -le 0 -or ($storeVersionNumbers | Where-Object { $_ -gt 65535 }).Count -gt 0 -or $storeVersionNumbers[3] -ne 0) {
        throw "StoreVersion parts must be between 0 and 65535, the first part must be greater than 0, and the fourth part must be 0."
    }
    $Standalone = $true
}

function Invoke-CBMBuild {
    param(
        [string]$EntryFile,
        [string]$OutputFile,
        [string]$IconFile,
        [string]$ProductName,
        [string]$OutputDirectory
    )

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $videoVendor = Join-Path $projectRoot "cbm_editor\vendor\video"
    $videoTool = Join-Path $videoVendor "windows-x64\cbm_video_tool.exe"
    $videoFiles = @(
        $videoTool,
        (Join-Path $videoVendor "manifest.json"),
        (Join-Path $videoVendor "THIRD_PARTY_NOTICES.txt"),
        (Join-Path $videoVendor "LICENSE_FFMPEG_GPLv2.txt"),
        (Join-Path $videoVendor "LICENSE_X264.txt"),
        (Join-Path $videoVendor "LICENSE_LIBVPX.txt"),
        (Join-Path $videoVendor "LICENSE_DAV1D.txt"),
        (Join-Path $videoVendor "PATENTS_LIBVPX.txt")
    )
    foreach ($videoFile in $videoFiles) {
        if (-not (Test-Path -LiteralPath $videoFile -PathType Leaf)) {
            throw "Missing verified video helper artifact or license: $videoFile. Run scripts/build_video_tool.sh windows-x64 and scripts/verify_video_tool_windows.ps1 first."
        }
    }
    $videoManifest = Get-Content -LiteralPath (Join-Path $videoVendor "manifest.json") -Raw | ConvertFrom-Json
    $videoArtifact = $videoManifest.artifacts.'windows-x64'
    $actualVideoHash = (Get-FileHash -LiteralPath $videoTool -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($videoArtifact.scan) -or $actualVideoHash -ne $videoArtifact.sha256.ToLowerInvariant()) {
        throw "cbm_video_tool must pass verification and Microsoft Defender scanning before it can be packaged."
    }
    $description = "Custom Beatmaps Editor"
    $copyright = "Copyright $([char]0x00A9) 2026 Splash!"
    $buildMode = if ($Standalone) { "--mode=standalone" } else { "--onefile" }

    $nuitkaArgs = @(
        "-m",
        "nuitka",
        $buildMode
    )
    if (-not $Standalone) {
        if ($NoCompression) {
            $nuitkaArgs += "--onefile-no-compression"
        }
        if ($AsArchive) {
            $nuitkaArgs += "--onefile-as-archive"
        }
        if ($NoDll) {
            $nuitkaArgs += "--onefile-no-dll"
        }
    }
    $nuitkaArgs += @(
        "--lto=yes",
        "--assume-yes-for-downloads",
        "--enable-plugin=pyqt6",
        "--include-qt-plugins=multimedia",
        "--include-module=PyQt6.QtMultimedia",
        "--include-package=cbm_editor",
        "--windows-console-mode=disable",
        "--file-version=$fileVersion",
        "--product-version=$fileVersion",
        "--file-description=$description",
        "--copyright=$copyright",
        "--company-name=Splash!",
        "--product-name=$ProductName",
        "--windows-icon-from-ico=$IconFile",
        "--include-data-dir=cbm_editor/sounds=cbm_editor/sounds",
        "--noinclude-data-files=cbm_editor/sounds/backgrounds/**",
        "--include-data-dir=cbm_editor/fonts=cbm_editor/fonts",
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
        "--include-data-file=cbm_editor/vendor/video/manifest.json=cbm_editor/vendor/video/manifest.json",
        "--include-data-file=cbm_editor/vendor/video/THIRD_PARTY_NOTICES.txt=cbm_editor/vendor/video/THIRD_PARTY_NOTICES.txt",
        "--include-data-file=cbm_editor/vendor/video/LICENSE_FFMPEG_GPLv2.txt=cbm_editor/vendor/video/LICENSE_FFMPEG_GPLv2.txt",
        "--include-data-file=cbm_editor/vendor/video/LICENSE_X264.txt=cbm_editor/vendor/video/LICENSE_X264.txt",
        "--include-data-file=cbm_editor/vendor/video/LICENSE_LIBVPX.txt=cbm_editor/vendor/video/LICENSE_LIBVPX.txt",
        "--include-data-file=cbm_editor/vendor/video/LICENSE_DAV1D.txt=cbm_editor/vendor/video/LICENSE_DAV1D.txt",
        "--include-data-file=cbm_editor/vendor/video/PATENTS_LIBVPX.txt=cbm_editor/vendor/video/PATENTS_LIBVPX.txt",
        "--include-data-file=cbm_editor/vendor/video/windows-x64/cbm_video_tool.exe=cbm_editor/vendor/video/windows-x64/cbm_video_tool.exe",
        "--output-dir=$OutputDirectory",
        "--output-filename=$OutputFile",
        $EntryFile
    )

    Push-Location $projectRoot
    try {
        & $PythonExe @nuitkaArgs
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    } finally {
        Pop-Location
    }

    if ($Standalone) {
        return
    }
    $builtExecutable = Join-Path $OutputDirectory $OutputFile
    if (-not (Test-Path -LiteralPath $builtExecutable -PathType Leaf)) {
        throw "Nuitka completed without creating the expected executable: $builtExecutable"
    }
    if (-not [string]::IsNullOrWhiteSpace($SigningCertificatePath)) {
        $resolvedSigningCertificate = [System.IO.Path]::GetFullPath($SigningCertificatePath)
        if (-not (Test-Path -LiteralPath $resolvedSigningCertificate -PathType Leaf)) {
            throw "Signing certificate not found: $resolvedSigningCertificate"
        }
        $signTool = Get-WindowsSdkToolPath "SignTool.exe"
        $signArguments = @(
            "sign",
            "/fd", "SHA256",
            "/tr", "http://timestamp.digicert.com",
            "/td", "SHA256",
            "/f", $resolvedSigningCertificate,
            "/p", $SigningCertificatePassword,
            "/d", $ProductName,
            $builtExecutable
        )
        & $signTool @signArguments
        if ($LASTEXITCODE -ne 0) {
            throw "SignTool failed to sign $builtExecutable."
        }
        $signature = Get-AuthenticodeSignature -LiteralPath $builtExecutable
        if ($null -eq $signature.SignerCertificate) {
            throw "The generated executable does not contain an Authenticode signature: $builtExecutable"
        }
        Write-Host "Signed executable: $builtExecutable"
    }
    $archiveFilename = "$([System.IO.Path]::GetFileNameWithoutExtension($OutputFile)).zip"
    $archivePath = Join-Path $OutputDirectory $archiveFilename
    Compress-Archive -LiteralPath $builtExecutable -DestinationPath $archivePath -CompressionLevel Optimal -Force
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        if ($archive.Entries.Count -ne 1 -or $archive.Entries[0].FullName -ne $OutputFile -or $archive.Entries[0].Length -ne (Get-Item -LiteralPath $builtExecutable).Length) {
            throw "The Windows release ZIP is invalid: $archivePath"
        }
    } finally {
        $archive.Dispose()
    }
}

function Get-WindowsSdkToolPath {
    param([string]$Name)
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $sdkRoot = "C:\Program Files (x86)\Windows Kits\10\bin"
    if (-not (Test-Path -LiteralPath $sdkRoot -PathType Container)) {
        throw "$Name was not found. Install the Windows SDK."
    }
    $candidates = Get-ChildItem -LiteralPath $sdkRoot -Directory | Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } | Sort-Object { [version]$_.Name } -Descending
    foreach ($candidate in $candidates) {
        $path = Join-Path $candidate.FullName "x64\$Name"
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            return $path
        }
    }
    throw "$Name was not found. Install the Windows SDK."
}

function Get-MakeAppxPath {
    return Get-WindowsSdkToolPath "MakeAppx.exe"
}

function Get-MakePriPath {
    return Get-WindowsSdkToolPath "MakePri.exe"
}

function New-CBMStoreAsset {
    param(
        [System.Drawing.Image]$Source,
        [int]$Size,
        [string]$Destination
    )
    $bitmap = [System.Drawing.Bitmap]::new($Size, $Size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    try {
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        try {
            $graphics.Clear([System.Drawing.Color]::Transparent)
            $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
            $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
            $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
            $graphics.DrawImage($Source, 0, 0, $Size, $Size)
        } finally {
            $graphics.Dispose()
        }
        $bitmap.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
    } finally {
        $bitmap.Dispose()
    }
}

function Invoke-CBMStorePackage {
    param(
        [string]$BuildOutputDirectory,
        [string]$ExecutableName,
        [string]$DisplayName,
        [string]$Description,
        [string]$ApplicationId,
        [string]$AssetSource,
        [string]$PackageBaseName
    )
    $executables = @(Get-ChildItem -LiteralPath $BuildOutputDirectory -Recurse -File -Filter $ExecutableName | Where-Object { $_.Directory.Name.EndsWith('.dist', [System.StringComparison]::OrdinalIgnoreCase) })
    if ($executables.Count -ne 1) {
        throw "Expected exactly one standalone $ExecutableName in $BuildOutputDirectory, found $($executables.Count)."
    }
    $distributionDirectory = $executables[0].Directory.FullName
    $stagingDirectory = [System.IO.Path]::GetFullPath((Join-Path $BuildOutputDirectory "msix-staging"))
    $resolvedBuildOutput = [System.IO.Path]::GetFullPath($BuildOutputDirectory).TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
    if (-not $stagingDirectory.StartsWith($resolvedBuildOutput, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "The MSIX staging directory is outside the Store build output."
    }
    if (Test-Path -LiteralPath $stagingDirectory) {
        Remove-Item -LiteralPath $stagingDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $stagingDirectory -Force | Out-Null
    Get-ChildItem -LiteralPath $distributionDirectory -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $stagingDirectory -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination (Join-Path $stagingDirectory "LICENSE.txt") -Force

    $assetsDirectory = Join-Path $stagingDirectory "Assets"
    New-Item -ItemType Directory -Path $assetsDirectory -Force | Out-Null
    Add-Type -AssemblyName System.Drawing
    $sourceImage = [System.Drawing.Image]::FromFile((Join-Path $projectRoot $AssetSource))
    try {
        New-CBMStoreAsset $sourceImage 44 (Join-Path $assetsDirectory "Square44x44Logo.png")
        New-CBMStoreAsset $sourceImage 50 (Join-Path $assetsDirectory "StoreLogo.png")
        New-CBMStoreAsset $sourceImage 150 (Join-Path $assetsDirectory "Square150x150Logo.png")
        foreach ($scale in @(100, 200, 400)) {
            New-CBMStoreAsset $sourceImage ([int](44 * $scale / 100)) (Join-Path $assetsDirectory "Square44x44Logo.scale-$scale.png")
            New-CBMStoreAsset $sourceImage ([int](50 * $scale / 100)) (Join-Path $assetsDirectory "StoreLogo.scale-$scale.png")
            New-CBMStoreAsset $sourceImage ([int](150 * $scale / 100)) (Join-Path $assetsDirectory "Square150x150Logo.scale-$scale.png")
        }
        foreach ($size in @(16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256)) {
            New-CBMStoreAsset $sourceImage $size (Join-Path $assetsDirectory "Square44x44Logo.targetsize-$size.png")
            New-CBMStoreAsset $sourceImage $size (Join-Path $assetsDirectory "Square44x44Logo.targetsize-${size}_altform-unplated.png")
            New-CBMStoreAsset $sourceImage $size (Join-Path $assetsDirectory "Square44x44Logo.targetsize-${size}_altform-lightunplated.png")
        }
    } finally {
        $sourceImage.Dispose()
    }

    $identityName = [System.Security.SecurityElement]::Escape($StoreIdentityName)
    $publisher = [System.Security.SecurityElement]::Escape($StorePublisher)
    $publisherDisplayName = [System.Security.SecurityElement]::Escape($StorePublisherDisplayName)
    $escapedDisplayName = [System.Security.SecurityElement]::Escape($DisplayName)
    $escapedDescription = [System.Security.SecurityElement]::Escape($Description)
    $manifest = @"
<?xml version="1.0" encoding="utf-8"?>
<Package xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10" xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10" xmlns:uap10="http://schemas.microsoft.com/appx/manifest/uap/windows10/10" xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities" IgnorableNamespaces="uap uap10 rescap">
  <Identity Name="$identityName" Publisher="$publisher" Version="$StoreVersion" ProcessorArchitecture="x64" />
  <Properties>
    <DisplayName>$escapedDisplayName</DisplayName>
    <PublisherDisplayName>$publisherDisplayName</PublisherDisplayName>
    <Description>$escapedDescription</Description>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>
  <Resources>
    <Resource Language="en-us" />
  </Resources>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Applications>
    <Application Id="$ApplicationId" Executable="$ExecutableName" uap10:RuntimeBehavior="packagedClassicApp" uap10:TrustLevel="mediumIL">
      <uap:VisualElements DisplayName="$escapedDisplayName" Description="$escapedDescription" BackgroundColor="transparent" Square150x150Logo="Assets\Square150x150Logo.png" Square44x44Logo="Assets\Square44x44Logo.png" />
    </Application>
  </Applications>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"@
    $manifestPath = Join-Path $stagingDirectory "AppxManifest.xml"
    [System.IO.File]::WriteAllText($manifestPath, $manifest, (New-Object System.Text.UTF8Encoding($false)))

    $makePri = Get-MakePriPath
    $priConfigPath = Join-Path $stagingDirectory "priconfig.xml"
    $resourcesPriPath = Join-Path $stagingDirectory "resources.pri"
    & $makePri createconfig /cf $priConfigPath /dq en-US /o
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $priConfigPath -PathType Leaf)) {
        throw "MakePri failed to create the package resource configuration."
    }
    try {
        & $makePri new /pr $stagingDirectory /cf $priConfigPath /mn $manifestPath /of $resourcesPriPath /o
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $resourcesPriPath -PathType Leaf)) {
            throw "MakePri failed to index the Microsoft Store package resources."
        }
    } finally {
        Remove-Item -LiteralPath $priConfigPath -Force -ErrorAction SilentlyContinue
    }

    $makeAppx = Get-MakeAppxPath
    $packagePath = Join-Path $BuildOutputDirectory "${PackageBaseName}_${StoreVersion}_x64.msix"
    if (Test-Path -LiteralPath $packagePath) {
        Remove-Item -LiteralPath $packagePath -Force
    }
    & $makeAppx pack /d $stagingDirectory /p $packagePath /o
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $packagePath -PathType Leaf)) {
        throw "MakeAppx failed to create the Microsoft Store package."
    }
    Write-Host "Microsoft Store package created: $packagePath"
}

if ($MicrosoftStore) {
    if ($Edition -eq "Preview") {
        $storeOutputDirectory = Join-Path $resolvedOutputRoot "store\preview"
        Invoke-CBMBuild "scripts\CBM_Editor_store_preview.py" "CBM_Editor.exe" "scripts\icon_pre.ico" "CBM Editor Preview" $storeOutputDirectory
        Invoke-CBMStorePackage $storeOutputDirectory "CBM_Editor.exe" "CBM Editor Preview" "Custom Beatmaps Editor Preview" "CBMEditorPreview" "cbm_editor\sounds\icon_pre.png" "CBM_Editor_Preview"
    } else {
        $storeOutputDirectory = Join-Path $resolvedOutputRoot "store\release"
        Invoke-CBMBuild "scripts\CBM_Editor_store.py" "CBM_Editor.exe" "scripts\icon.ico" "CBM Editor" $storeOutputDirectory
        Invoke-CBMStorePackage $storeOutputDirectory "CBM_Editor.exe" "CBM Editor" "Custom Beatmaps Editor" "CBMEditor" "images\CBM_Editor_Icon.png" "CBM_Editor"
    }
    return
}

if ($Edition -in @("Preview", "Both")) {
    if ([string]::IsNullOrWhiteSpace($PreviewOutputFile)) {
        if ([string]::IsNullOrWhiteSpace($PreviewVersion)) {
            throw "PreviewVersion is required for preview builds."
        }
        $PreviewOutputFile = "CBM_Editor_v${appVersion}-pre${PreviewVersion}.exe"
    }
    Invoke-CBMBuild "scripts\CBM_Editor_preview.py" $PreviewOutputFile "scripts\icon_pre.ico" "CBM Editor -PREVIEW-" (Join-Path $resolvedOutputRoot "preview")
}

if ($Edition -in @("Release", "Both")) {
    Invoke-CBMBuild "scripts\CBM_Editor_release.py" "CBM_Editor_v${appVersion}.exe" "scripts\icon.ico" "CBM Editor" (Join-Path $resolvedOutputRoot "release")
}
