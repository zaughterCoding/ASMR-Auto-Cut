<#
.SYNOPSIS
    用 PyInstaller 把后端冻结到 src-tauri/resources/backend/。

.DESCRIPTION
    两件事：跑冻结、补回占位文件。

    补占位文件不是可有可无的收尾：PyInstaller 的 COLLECT 在 --noconfirm 下会先
    `Removing dir` 再重建产物目录，把 resources/backend/.gitkeep 一起删掉。
    那个文件是**必须进版本管理**的——tauri-build 对「不存在的 resources 路径」
    是硬报错，缺了它连 `tauri dev` 都编译不过。所以每次冻结之后都要写回去。

    产物目录本身（98 MB 上下）不进版本管理，见 .gitignore。

.EXAMPLE
    powershell -File app/scripts/freeze-backend.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$RepoRoot   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PyInstaller = Join-Path $RepoRoot '.venv/Scripts/pyinstaller.exe'
$Spec       = Join-Path $RepoRoot 'backend/packaging/asmr-auto-cut.spec'
$DistPath   = Join-Path $RepoRoot 'app/src-tauri/resources'
# 中间产物也留在项目盘上，不落到 C 盘的用户缓存。
$WorkPath   = Join-Path $RepoRoot 'backend/build/pyinstaller'

if (-not (Test-Path $PyInstaller)) {
    throw "找不到 $PyInstaller。先装开发依赖：.venv\Scripts\python.exe -m pip install -e `".\backend[dev]`""
}

Write-Host '==> 冻结后端（PyInstaller onedir）' -ForegroundColor Cyan
$sw = [Diagnostics.Stopwatch]::StartNew()
& $PyInstaller $Spec --noconfirm --clean --distpath $DistPath --workpath $WorkPath
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败，退出码 $LASTEXITCODE" }
Write-Host ("    耗时 {0:N1} 秒" -f $sw.Elapsed.TotalSeconds) -ForegroundColor DarkGray

$exe = Join-Path $DistPath 'backend/asmr-auto-cut.exe'
if (-not (Test-Path $exe)) { throw "冻结没产出入口 exe：$exe" }

# COLLECT 删过目录，把占位文件补回去（原因见文件头注释）。
$placeholder = Join-Path $DistPath 'backend/.gitkeep'
if (-not (Test-Path $placeholder)) {
    New-Item -ItemType File -Force -Path $placeholder | Out-Null
    Write-Host '    已补回 resources/backend/.gitkeep' -ForegroundColor DarkGray
}

$size = (Get-ChildItem (Join-Path $DistPath 'backend') -Recurse -File |
         Measure-Object -Property Length -Sum).Sum
Write-Host ("冻结完成，{0:N1} MB -> app/src-tauri/resources/backend/" -f ($size / 1MB)) -ForegroundColor Green
