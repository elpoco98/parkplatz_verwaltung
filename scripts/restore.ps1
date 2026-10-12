param([Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference = "Stop"
$resolvedSource = (Resolve-Path $Source).Path
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    docker compose stop web
    if ($LASTEXITCODE -ne 0) { throw "Stoppen der Web-App fehlgeschlagen." }
    docker compose cp $resolvedSource db:/tmp/parking-restore.dump
    if ($LASTEXITCODE -ne 0) { throw "Kopieren der Sicherung fehlgeschlagen; Web-App bleibt angehalten." }
    docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --single-transaction /tmp/parking-restore.dump'
    if ($LASTEXITCODE -ne 0) { throw "Wiederherstellung fehlgeschlagen; Web-App bleibt angehalten." }
    docker compose up -d web
    if ($LASTEXITCODE -ne 0) { throw "Neustart der Web-App fehlgeschlagen." }
    Write-Host "Sicherung wiederhergestellt."
} finally { Pop-Location }
