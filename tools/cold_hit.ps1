# Time the first screen and one analyse request against a deployed URL, once, with curl's own timers.
# Usage: powershell -File tools/cold_hit.ps1 -Url https://example.vercel.app [-Out result.txt]
# For the host gate, run it once after the deployment has had no requests for 24 hours, then record the
# output in docs/KIRO-LOG.md. curl reports a timing even when a request fails, so a single shot is never lost.
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [string]$Sample = "",
    [string]$Out = ""
)
$repo = (Resolve-Path "$PSScriptRoot\..").Path
if (-not $Sample) { $Sample = Join-Path $repo "spike\samples\mystery_a" }
$Url = $Url.TrimEnd("/")
$fmt = "HTTP %{http_code} connect %{time_connect}s first_byte %{time_starttransfer}s total %{time_total}s"
$started = (Get-Date).ToUniversalTime()
$page = curl.exe -s -o NUL -m 120 -w $fmt "$Url/"
$body = Join-Path $env:TEMP "cold_hit_body.json"
$api = curl.exe -s -o $body -m 120 -w $fmt -X POST --data-binary "@$Sample" `
    -H "Content-Type: application/octet-stream" "$Url/api/analyze"
$lines = @(
    "url:             $Url",
    ("started_utc:     {0:u}" -f $started),
    "first_screen:    $page",
    "analyse(sample): $api",
    "body (first 300 chars): $(if (Test-Path $body) { $t = Get-Content $body -Raw; $t.Substring(0, [Math]::Min(300, $t.Length)) } else { '(none)' })"
)
if ($Out) { $lines | Set-Content -Path $Out -Encoding utf8 }
$lines
