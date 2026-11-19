# Time the first screen and one analyse request against the deployed URL.
# Usage: powershell -File tools/cold_hit.ps1 -Url https://example.vercel.app
# Run it after the deployment has had no requests for 24 hours. Record the output in docs/KIRO-LOG.md.
param(
    [Parameter(Mandatory = $true)][string]$Url,
    [string]$Sample = "spike/samples/mystery_a"
)
$Url = $Url.TrimEnd("/")
$bytes = [IO.File]::ReadAllBytes((Resolve-Path $Sample))
$page = Measure-Command { $r1 = Invoke-WebRequest -Uri "$Url/" -UseBasicParsing }
$api = Measure-Command {
    $r2 = Invoke-WebRequest -Uri "$Url/api/analyze" -Method Post -Body $bytes `
        -ContentType "application/octet-stream" -UseBasicParsing
}
"date_utc:        {0:u}" -f (Get-Date).ToUniversalTime()
"first_screen:    HTTP {0} in {1:N2} s" -f $r1.StatusCode, $page.TotalSeconds
"analyse(sample): HTTP {0} in {1:N2} s" -f $r2.StatusCode, $api.TotalSeconds
"body:            $($r2.Content)"