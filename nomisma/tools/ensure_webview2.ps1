# For the clean GitHub Actions test machine. Installs only a missing runtime.
# https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

function Get-NomismaWebViewVersion {
    $client = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    $locations = @(
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$client",
        "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$client",
        "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$client"
    )
    foreach ($location in $locations) {
        $version = (Get-ItemProperty -LiteralPath $location -Name pv -ErrorAction SilentlyContinue).pv
        if ($version -match '^\d+\.\d+\.\d+\.\d+$' -and [version]$version -gt [version]'0.0.0.0') {
            return $version
        }
    }
    return $null
}

$installed = Get-NomismaWebViewVersion
if ($installed) {
    Write-Host "WebView2 Runtime $installed is installed."
    return
}

$downloadRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$bootstrapper = Join-Path $downloadRoot "Nomisma-WebView2-$([Guid]::NewGuid().ToString('N')).exe"
try {
    Invoke-WebRequest -Uri 'https://go.microsoft.com/fwlink/p/?LinkId=2124703' -OutFile $bootstrapper -TimeoutSec 120
    $signature = Get-AuthenticodeSignature -LiteralPath $bootstrapper
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Microsoft Corporation(,|$)') {
        throw 'The WebView2 download does not have a valid Microsoft signature.'
    }
    $process = Start-Process -FilePath $bootstrapper -ArgumentList '/silent', '/install' -PassThru
    if (-not $process.WaitForExit(180000)) {
        $process.Kill()
        throw 'WebView2 installation did not finish within three minutes.'
    }
    if ($process.ExitCode -ne 0) {
        throw "WebView2 installation failed with exit code $($process.ExitCode)."
    }
    $installed = Get-NomismaWebViewVersion
    if (-not $installed) { throw 'WebView2 Runtime is still unavailable after installation.' }
    Write-Host "Installed WebView2 Runtime $installed."
} finally {
    Remove-Item -LiteralPath $bootstrapper -Force -ErrorAction SilentlyContinue
}
