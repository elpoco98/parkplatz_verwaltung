param([string]$Destination = "parking.dump")
$ErrorActionPreference = "Stop"
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/parking-backup.dump'
    if ($LASTEXITCODE -ne 0) { throw "pg_dump fehlgeschlagen." }
    docker compose cp db:/tmp/parking-backup.dump $Destination
    if ($LASTEXITCODE -ne 0) { throw "Kopieren der Sicherung fehlgeschlagen." }
    Write-Host "Sicherung erstellt: $Destination"
} finally { Pop-Location }
