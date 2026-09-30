$ErrorActionPreference = 'Stop'
python -m PyInstaller --noconfirm --clean packaging/SpotifyExporter.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
$exe = Join-Path (Resolve-Path dist) 'SpotifyExporter.exe'
# The windowed application reports via JSON because it has no console streams.
$env:QT_QPA_PLATFORM = 'offscreen'
$report = Join-Path (Resolve-Path dist) 'smoke-report.json'
$process = Start-Process -FilePath $exe -ArgumentList @('--smoke-test', '--smoke-report', "`"$report`"") -PassThru
if (-not $process.WaitForExit(90000)) {
  & taskkill /PID $process.Id /T /F
  throw 'Packaged executable smoke test timed out'
}
if ($process.ExitCode -ne 0) { throw "Smoke test exited with $($process.ExitCode)" }
$result = Get-Content $report -Raw | ConvertFrom-Json
if ($result.status -ne 'passed' -or $result.network -ne 'blocked' -or $result.export_formats -ne 4) {
  throw 'Packaged executable smoke report failed validation'
}
Get-Content $report
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  SpotifyExporter.exe" | Set-Content -Encoding ascii dist/SHA256SUMS.txt
python -m pip freeze | Set-Content -Encoding utf8 dist/build-dependencies.txt
Get-Content dist/SHA256SUMS.txt
