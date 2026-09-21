<#
.SYNOPSIS
    取回打包用的 LGPL FFmpeg 构建，落位到 src-tauri/resources/ffmpeg/。

.DESCRIPTION
    产物本身不进版本管理（见 .gitignore），所以这个脚本就是那份产物的出处：
    固定 URL、固定版本、可重复执行。

    为什么是 LGPL 而不是随手拿本机那份：项目只用 -c:v copy / -c:a aac / afade /
    concat / -vn / -map，一个 GPL 编码器都不需要。LGPL 构建既避开 GPL 的分发义务，
    又能和本仓库的 MIT 许可证相容。

    为什么是 shared 而不是 static：shared 压缩包 72.8 MB，解压后 DLL 平铺；
    static 那份单文件 164 MB，没有更小。

.PARAMETER Force
    已经落位过也重新下载并覆盖。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File app/scripts/vendor-ffmpeg.ps1
#>
[CmdletBinding()]
param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

#: 钉在 9.0 分支而不是浮动的 master，让产物可复现。
$Version = 'n9.0'
$Asset   = "ffmpeg-$Version-latest-win64-lgpl-shared-9.0.zip"
$Url     = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/$Asset"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$CacheDir = Join-Path $RepoRoot '.cache'
$DestDir  = Join-Path $RepoRoot 'app/src-tauri/resources/ffmpeg'
$Archive  = Join-Path $CacheDir $Asset
$Unpacked = Join-Path $CacheDir 'unpacked'

#: 丢掉 ffplay.exe（18.7 MB）——它是播放器，跟命令行转码无关。
#: 其余 DLL 全部保留：它们是 ffmpeg.exe 的静态导入，缺一个 exe 就起不来。
$DropExe = 'ffplay.exe'

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

Write-Step "FFmpeg $Version (LGPL shared, win64)"

if ((Test-Path $DestDir) -and -not $Force) {
    $existing = Get-ChildItem $DestDir -Filter 'ffmpeg.exe' -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "    已落位，跳过。要重取加 -Force。" -ForegroundColor Yellow
        exit 0
    }
}

New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
New-Item -ItemType Directory -Force -Path $DestDir  | Out-Null

if (-not (Test-Path $Archive)) {
    Write-Step "下载 $Asset"
    Invoke-WebRequest -Uri $Url -OutFile $Archive -UseBasicParsing
} else {
    Write-Host "    复用缓存 $Archive" -ForegroundColor DarkGray
}
Write-Host ("    压缩包 {0:N1} MB" -f ((Get-Item $Archive).Length / 1MB)) -ForegroundColor DarkGray

Write-Step "解压"
if (Test-Path $Unpacked) { Remove-Item -Recurse -Force $Unpacked }
Expand-Archive -Path $Archive -DestinationPath $Unpacked -Force

$root = Get-ChildItem $Unpacked -Directory | Select-Object -First 1
$bin  = Join-Path $root.FullName 'bin'
if (-not (Test-Path $bin)) { throw "压缩包结构不符预期，找不到 $bin" }

# DLL 必须和 exe 同目录平铺：Windows 先查 exe 自身所在目录，
# 放子目录会变成「找不到 avcodec-63.dll」。
Write-Step "落位到 app/src-tauri/resources/ffmpeg/"
Get-ChildItem $bin -File | Where-Object { $_.Name -ne $DropExe } | ForEach-Object {
    Copy-Item $_.FullName -Destination $DestDir -Force
    Write-Host ("    {0,-24} {1,10:N1} MB" -f $_.Name, ($_.Length / 1MB)) -ForegroundColor DarkGray
}

# LGPLv3 要求随二进制提供许可证文本。
Copy-Item (Join-Path $root.FullName 'LICENSE.txt') -Destination $DestDir -Force
Write-Host "    LICENSE.txt              (LGPLv3，随包分发)" -ForegroundColor DarkGray

Write-Step "校验所需能力"
$ffmpeg = Join-Path $DestDir 'ffmpeg.exe'
$checks = @(
    @{ Name = 'aac 编码器';   Args = @('-encoders');  Pattern = ' aac '  },
    @{ Name = 'afade 滤镜';   Args = @('-filters');   Pattern = ' afade' },
    @{ Name = 'concat 解复用'; Args = @('-demuxers'); Pattern = ' concat' },
    @{ Name = 'hevc 解码器';  Args = @('-decoders');  Pattern = ' hevc' }
)
$missing = @()
foreach ($check in $checks) {
    $output = & $ffmpeg -hide_banner @($check.Args) 2>&1 | Out-String
    if ($output -match [regex]::Escape($check.Pattern)) {
        Write-Host "    ✓ $($check.Name)" -ForegroundColor Green
    } else {
        Write-Host "    ✗ $($check.Name) 缺失" -ForegroundColor Red
        $missing += $check.Name
    }
}

# GPL 组件一旦被启用，分发义务就和本仓库的 MIT 许可证冲突。
$config = & $ffmpeg -hide_banner -version 2>&1 | Select-String '^configuration:'
if ($config -match '--enable-gpl') {
    throw "取到的是 GPL 构建，与 MIT 许可证不相容：$config"
} else {
    Write-Host "    ✓ 无 --enable-gpl（LGPL 构建）" -ForegroundColor Green
}

if ($missing.Count -gt 0) { throw "缺少：$($missing -join '、')" }

$total = (Get-ChildItem $DestDir -File | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host ("落位完成，共 {0:N1} MB" -f ($total / 1MB)) -ForegroundColor Green
