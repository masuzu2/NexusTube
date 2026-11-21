# Build NexusTube auto-update package - run from project folder: .\make-app-update.ps1
# Output: update-package\version.json + app-update.zip (index.js, src, web, node_modules prod, icon, package.json)
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
Set-Location $root

$pkg = Get-Content "$root\package.json" -Raw | ConvertFrom-Json
$version = $pkg.version
$outDir = Join-Path $root "update-package"
$stage = Join-Path $outDir "stage"
New-Item -ItemType Directory -Force $outDir | Out-Null

# 1) version.json
@{ version = $version; notes = "" } | ConvertTo-Json -Compress |
  Set-Content (Join-Path $outDir "version.json") -Encoding ascii

# 2) stage
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $stage | Out-Null

Copy-Item "$root\index.js" $stage
Copy-Item "$root\package.json" $stage
Copy-Item "$root\icon.ico" $stage
Copy-Item "$root\src" "$stage\src" -Recurse -Force
Copy-Item "$root\web" "$stage\web" -Recurse -Force

# 3) production node_modules (music-metadata, node-id3 + deps)
Push-Location $stage
npm install --omit=dev --ignore-scripts --no-audit --no-fund 2>&1 | Out-Null
Pop-Location

# 4) zip (tar ใน Windows 10/11 ทำ zip ไม่ได้ ใช้ Compress-Archive)
Remove-Item (Join-Path $outDir "app-update.zip") -Force -ErrorAction SilentlyContinue
Compress-Archive -Path "$stage\*" -DestinationPath (Join-Path $outDir "app-update.zip") -Force
Remove-Item $stage -Recurse -Force

$zip = Get-Item (Join-Path $outDir "app-update.zip")
Write-Host "Done v$version : version.json + app-update.zip ($([math]::Round($zip.Length/1MB,1)) MB)"
Write-Host "Upload: gh release create v$version update-package/version.json update-package/app-update.zip --repo masuzu2/NexusTube --title v$version"
