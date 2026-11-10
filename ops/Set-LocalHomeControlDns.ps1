#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
$domain = 'salavat.home.ro'
$address = '192.168.50.101'
$hostsFile = Join-Path $env:windir 'System32\drivers\etc\hosts'
$resultFile = Join-Path $PSScriptRoot 'local-dns-result.json'

try {
    $probe = & curl.exe --noproxy '*' --resolve "${domain}:443:${address}" --max-time 10 --silent --show-error --output NUL --write-out '%{http_code}' "https://${domain}/casa/"
    if ($LASTEXITCODE -ne 0 -or $probe -ne '200') {
        throw 'Pi5 nu este accesibil prin LAN. Fisierul hosts nu a fost modificat.'
    }

    $addresses = @(foreach ($line in Get-Content -LiteralPath $hostsFile) {
        $parts = (($line -split '#', 2)[0].Trim() -split '\s+')
        if ($parts.Count -ge 2 -and $parts[1..($parts.Count - 1)] -contains $domain) {
            $parts[0]
        }
    })
    if (@($addresses | Where-Object { $_ -ne $address }).Count) {
        throw 'Exista deja o mapare diferita pentru domeniu. Este necesara verificarea ei manuala.'
    }

    $backup = $null
    if ($addresses.Count -eq 0) {
        $backup = $hostsFile + '.casa-salavat-' + (Get-Date -Format 'yyyyMMddHHmmss') + '.bak'
        Copy-Item -LiteralPath $hostsFile -Destination $backup
        Add-Content -LiteralPath $hostsFile -Encoding ascii -Value "`r`n$address`t$domain # Casa Salavat - direct LAN; HTTPS retained"
    }
    Clear-DnsClientCache
    $status = & curl.exe --noproxy '*' --max-time 10 --silent --show-error --output NUL --write-out '%{http_code}' "https://${domain}/casa/"
    if ($LASTEXITCODE -ne 0 -or $status -ne '200') {
        throw 'Maparea este salvata, dar verificarea HTTPS a esuat. Verifica reteaua locala.'
    }
    @{ success = $true; status = $status; domain = $domain; address = $address; backup = $backup } |
        ConvertTo-Json | Set-Content -LiteralPath $resultFile -Encoding utf8
    exit 0
} catch {
    @{ success = $false; error = $_.Exception.Message } |
        ConvertTo-Json | Set-Content -LiteralPath $resultFile -Encoding utf8
    exit 1
}
