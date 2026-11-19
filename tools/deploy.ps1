# Deploy the committed HEAD to the Vercel project "necropsy" from a clean clone, never from the working tree.
# Step 1 commits docs/KIRO-LOG.md if the usage hook has dirtied it. Any other uncommitted change stops the deploy.
# Never deploys necropsy-coldtest: that project is the untouched host-gate canary.
# Usage: powershell -File tools/deploy.ps1      Output: the deployment log path and the production URL.
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $repo

# 1. KIRO-LOG.md first
if (git status --porcelain -- docs/KIRO-LOG.md) {
    git add docs/KIRO-LOG.md
    git commit -q -m "Log: Kiro usage before deploy" -- docs/KIRO-LOG.md
    Write-Output "committed docs/KIRO-LOG.md"
}
# 2. Nothing else may be uncommitted
$dirty = git status --porcelain
if ($dirty) { Write-Output "Uncommitted changes, not deploying:"; $dirty; exit 1 }

# 3. Clean clone of HEAD, linked to necropsy
$sha = (git rev-parse --short HEAD)
$dir = Join-Path $env:TEMP "necropsy-deploy-$sha"
if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
git clone -q --no-hardlinks $repo $dir
New-Item -ItemType Directory (Join-Path $dir ".vercel") | Out-Null
$link = Get-Content (Join-Path $repo ".vercel\project.json") -Raw | ConvertFrom-Json
if ($link.projectName -ne "necropsy") { Write-Output "Linked project is '$($link.projectName)', expected 'necropsy'."; exit 1 }
Copy-Item (Join-Path $repo ".vercel\project.json") (Join-Path $dir ".vercel\project.json")

# 4. Deploy
$log = Join-Path $env:TEMP "necropsy-deploy-$sha.log"
cmd /c "cd /d `"$dir`" && npx --yes vercel@66.2.0 deploy --prod --yes > `"$log`" 2>&1"
Write-Output "commit $sha, log $log"
Select-String -Path $log -Pattern "Aliased|Ready|Error" | ForEach-Object { $_.Line.Trim() }