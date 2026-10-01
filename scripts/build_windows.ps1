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
# Exercise actual Win32 window handles and native events as well as offscreen rendering.
$env:QT_QPA_PLATFORM = 'windows'
$nativeReport = Join-Path (Resolve-Path dist) 'native-smoke-report.json'
$native = Start-Process -FilePath $exe -ArgumentList @('--smoke-test', '--smoke-report', "`"$nativeReport`"") -PassThru
if (-not $native.WaitForExit(90000)) {
  & taskkill /PID $native.Id /T /F
  throw 'Native Windows smoke test timed out'
}
if ($native.ExitCode -ne 0) { throw "Native Windows smoke exited with $($native.ExitCode)" }
$nativeResult = Get-Content $nativeReport -Raw | ConvertFrom-Json
if ($nativeResult.status -ne 'passed' -or $nativeResult.network -ne 'blocked' -or $nativeResult.qt_platform -ne 'windows') {
  throw 'Native Windows smoke report failed validation'
}
Get-Content $nativeReport
$env:QT_QPA_PLATFORM = 'offscreen'
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  SpotifyExporter.exe" | Set-Content -Encoding ascii dist/SHA256SUMS.txt
python -m pip freeze | Set-Content -Encoding utf8 dist/build-dependencies.txt
Get-Content dist/SHA256SUMS.txt
