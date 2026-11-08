# Warm-up: run once a day after submission so the free instance does not sleep
$url = "https://degree-compass.onrender.com/api/health"
for ($i = 1; $i -le 6; $i++) {
    try {
        $r = Invoke-WebRequest -Uri $url -TimeoutSec 90 -UseBasicParsing
        if ($r.StatusCode -eq 200) { Write-Host "ready: $($r.Content)"; break }
    } catch { Write-Host "attempt $i failed, retrying..."; Start-Sleep -Seconds 15 }
}
