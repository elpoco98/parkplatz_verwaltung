# Testbericht

Stand: 12.10.2026. Python 3.12, Django 5.2.18, qrcode 8.2.

## Ausgeführte Prüfungen

- Initiale Migration und Erweiterungsmigration für Fahrzeugtypen mit SQLite: erfolgreich.
- `manage.py check`: keine Probleme.
- `makemigrations --check --dry-run`: keine fehlenden Schemaänderungen.
- `collectstatic`: lokale Dateien und WhiteNoise-Manifest aufgebaut.
- `manage.py test`: **58 Tests gefunden, 55 erfolgreich, 3 PostgreSQL-Tests übersprungen**.
- Ursprünglicher HTTP-Test mit tatsächlich gestartetem Gunicorn: Healthcheck, CSRF-Login, Dashboard und versionierte CSS-Auslieferung erfolgreich.
- Erweiterungs-HTTP-Test mit Gunicorn: Kalender, QR-Seite und tatsächliche SVG-Auslieferung erfolgreich.
- Die wiederholte Initialisierung verändert vorhandene Administratorpasswörter und Fahrzeuge nicht.

## Abdeckung

Bestehende Tests prüfen Reservierungsüberschneidungen, angrenzende Zeiträume, Stornierung, persönliche/Dispositionsrechte, Ausgabe und Rückgabe, Kilometerstände, doppelte Aktionen, Übernahme einer Reservierung, überfällige Nutzungen, inaktive Fahrzeuge, Versionskonflikte, Deaktivierungsregeln, Login, CSRF, GET-/POST-Regeln, Seitenrendering, CSV und Pagination.

Die Verfügbarkeitssuche prüft übergreifende und teilweise überschneidende Buchungen, geplante/überfällige Rückgaben, leere/ungültige Eingaben, leere Ergebnislisten, Übernahme der Zeiten und eine zwischen Suche und Reservierung hinzugekommene Buchung.

18 neue Tests für diese Erweiterung prüfen:

- Typ anlegen/umbenennen über die Admin-Konsole, Zuordnung, Schutz referenzierter Typen und Berechtigungen.
- Typfilter in Übersicht und Verfügbarkeit; bestehende Fahrzeuge ohne Typ.
- Ausgabe/Rückgabe ohne Parkplatznummern und Erhalt alter interner Werte.
- Kalender über mehrere Tage, exklusive Mitternachtsenden, Typ-/Fahrzeugfilter und Filtererhalt beim Monatswechsel.
- Stornierungen, übernommene Buchungen ohne doppelte Darstellung, Sommerzeit und überfällige Rückgaben.
- Ungültige Monatsfilter.
- Allgemeine und fahrzeugspezifische QR-Ziele, localhost-Hinweis, ungültige Konfiguration und fehlende Fahrzeuge.
- Tatsächliche SVG-Erzeugung, XML-Struktur, Download und Anmeldungspflicht.

## Verbleibende Prüfung auf dem Windows-PC

Docker ist in dieser Erstellungsumgebung nicht installiert. Kein Image-Build und kein Compose-Start wurden hier durchgeführt. SQLite prüft keine PostgreSQL-Zeilensperren. Die drei zusätzlichen PostgreSQL-Tests verwenden zwei gleichzeitige Threads für Reservierung, Ausgabe und Rückgabe.

Mit laufendem Stack:

```powershell
docker compose exec web python manage.py test --verbosity 2
```

Erwartung: alle 58 Tests erfolgreich, keine PostgreSQL-Tests übersprungen.

Eine visuelle Windows-Browserprüfung und ein physischer Handy-Scan wurden hier nicht durchgeführt. Das Scannen setzt die tatsächliche LAN-IP, Erreichbarkeit von Port 8080 und ein Benutzerkonto voraus. Die PowerShell-Sicherungs-/Wiederherstellungsskripte wurden hier nicht unter Windows ausgeführt.
