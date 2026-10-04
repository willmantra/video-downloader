param(
    [string]$Destination = (Join-Path $PSScriptRoot "dist\Video Downloader\bin")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$ytDlpPath = Join-Path $Destination "yt-dlp.exe"
Write-Host "Downloading yt-dlp..."
Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile $ytDlpPath

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("video-downloader-deps-" + [guid]::NewGuid().ToString("N"))
$ffmpegZip = Join-Path $tempRoot "ffmpeg.zip"
$ffmpegExtract = Join-Path $tempRoot "ffmpeg"

try {
    New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
    Write-Host "Downloading FFmpeg..."
    Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $ffmpegZip
    Expand-Archive -Path $ffmpegZip -DestinationPath $ffmpegExtract -Force

    $ffmpeg = Get-ChildItem -Path $ffmpegExtract -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
    $ffprobe = Get-ChildItem -Path $ffmpegExtract -Filter "ffprobe.exe" -Recurse | Select-Object -First 1

    if (-not $ffmpeg) { throw "ffmpeg.exe was not found in the downloaded FFmpeg archive." }
    if (-not $ffprobe) { throw "ffprobe.exe was not found in the downloaded FFmpeg archive." }

    Copy-Item $ffmpeg.FullName (Join-Path $Destination "ffmpeg.exe") -Force
    Copy-Item $ffprobe.FullName (Join-Path $Destination "ffprobe.exe") -Force
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Verifying bundled tools..."
& $ytDlpPath --version
& (Join-Path $Destination "ffmpeg.exe") -version | Select-Object -First 1
Write-Host "Bundled dependencies are ready in: $Destination"
