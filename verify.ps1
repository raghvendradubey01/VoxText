# End-to-end smoke test against a running VoxText server.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File verify.ps1
$ErrorActionPreference = 'Stop'
$base = 'http://127.0.0.1:8000'
$pass = 0
$fail = 0

function Check($label, $cond, $extra = '') {
    if ($cond) { $script:pass++; Write-Output "PASS  $label $extra" }
    else       { $script:fail++; Write-Output "FAIL  $label $extra" }
}

# 1. Health endpoint
$h = Invoke-WebRequest -UseBasicParsing "$base/api/health"
$j = $h.Content | ConvertFrom-Json
Check 'GET /api/health returns 200' ($h.StatusCode -eq 200)
Check 'health status is ok'         ($j.status -eq 'ok')
Write-Output "      app=$($j.app) version=$($j.version) model_ready=$($j.speech_model_ready)"

# 2. Anonymous dashboard redirects to /login
$anon = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -SkipHttpErrorCheck "$base/" -ErrorAction SilentlyContinue
Check 'GET / anonymous redirects 302' ($anon.StatusCode -eq 302) "Location=$($anon.Headers.Location)"

# 3. Public pages render
foreach ($p in '/login', '/signup') {
    $r = Invoke-WebRequest -UseBasicParsing "$base$p"
    Check "GET $p returns 200" ($r.StatusCode -eq 200)
}

# 4. Static assets served
$asset = Invoke-WebRequest -UseBasicParsing "$base/static/js/auth.js"
Check 'GET /static/js/auth.js returns 200' ($asset.StatusCode -eq 200)

# 5. Sign up (unique email each run)
$email = "smoke$(Get-Random -Maximum 999999)@example.com"
$body  = @{ email = $email; password = 'correct-horse-battery'; full_name = 'Smoke Test' } | ConvertTo-Json
$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
try {
    $su = Invoke-WebRequest -UseBasicParsing -Method Post -ContentType 'application/json' `
            -Body $body -WebSession $session "$base/api/auth/signup"
    Check 'POST /api/auth/signup returns 201' ($su.StatusCode -eq 201)
} catch {
    Check 'POST /api/auth/signup returns 201' $false $_.Exception.Message
}

# 6. Session cookie is HttpOnly
$cookie = $session.Cookies.GetCookies("$base/") | Where-Object { $_.Name -eq 'voxtext_session' }
Check 'session cookie issued'     ($null -ne $cookie)
Check 'session cookie is HttpOnly' ($cookie.HttpOnly -eq $true)

# 7. Authenticated /me
$me = Invoke-WebRequest -UseBasicParsing -WebSession $session "$base/api/auth/me"
Check 'GET /api/auth/me returns 200' ($me.StatusCode -eq 200)
Check '/me echoes the new email'     (($me.Content | ConvertFrom-Json).email -eq $email)

# 8. Authenticated dashboard
$dash = Invoke-WebRequest -UseBasicParsing -WebSession $session "$base/"
Check 'GET / while signed in returns 200' ($dash.StatusCode -eq 200)

# 9. Wrong password is rejected without distinguishing the account
$bad = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -SkipHttpErrorCheck -Method Post `
        -ContentType 'application/json' `
        -Body (@{ email = $email; password = 'definitely-wrong-1' } | ConvertTo-Json) `
        "$base/api/auth/login" -ErrorAction SilentlyContinue
Check 'POST /api/auth/login with bad password returns 401' ($bad.StatusCode -eq 401)

# 10. Transcription requires a session
$noAuth = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 -SkipHttpErrorCheck -Method Post `
           "$base/api/transcribe" -ErrorAction SilentlyContinue
Check 'POST /api/transcribe without session is refused' ($noAuth.StatusCode -in 401, 403, 422)

# 11. Logout clears the session
$lo = Invoke-WebRequest -UseBasicParsing -Method Post -WebSession $session "$base/api/auth/logout"
Check 'POST /api/auth/logout returns 204' ($lo.StatusCode -eq 204)

Write-Output ""
Write-Output "RESULT: $pass passed, $fail failed"
if ($fail -gt 0) { exit 1 }
