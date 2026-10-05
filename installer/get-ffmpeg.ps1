param([string]$Dest)
# Downloads FFmpeg (the video encoder Reel Maker uses for export) from the
# official imageio-ffmpeg package on PyPI and checks its SHA-256 fingerprint.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $url = 'https://files.pythonhosted.org/packages/2c/c6/fa760e12a2483469e2bf5058c5faff664acf66cadb4df2ad6205b016a73d/imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl'
    $sha = '02fa47c83703c37df6bfe4896aab339013f62bf02c5ebf2dce6da56af04ffc0a'
    $tmp = Join-Path $env:TEMP 'reelmaker_ffmpeg.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $tmp
    if ((Get-FileHash $tmp -Algorithm SHA256).Hash.ToLower() -ne $sha) { throw 'Download was damaged' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($tmp)
    $e = $z.Entries | Where-Object { $_.FullName -like 'imageio_ffmpeg/binaries/*.exe' } | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
    [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $Dest, $true)
    $z.Dispose()
    Remove-Item $tmp -Force
    exit 0
} catch {
    Write-Output $_.Exception.Message
    exit 1
}
