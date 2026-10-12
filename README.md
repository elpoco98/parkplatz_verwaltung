# ParkPilot – Fahrzeugverwaltung

Vollständige lokale Web-Anwendung für Windows-PCs mit Docker Compose, Django, Gunicorn und PostgreSQL. Mehrere Browser greifen auf denselben Server und dieselbe Datenbank zu. Für den ersten Image-Download und den Build ist Internet erforderlich; die Anwendung braucht keinen externen Dienst und kein Cloud-Konto.

## Schnellstart unter Windows (PowerShell)

Voraussetzung: Docker Desktop läuft mit Linux-Containern und Docker Compose v2. ZIP entpacken, PowerShell im Ordner mit `compose.yaml` öffnen:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps
```

Wenn `web` und `db` gesund (`healthy`) sind: **http://localhost:8080**.

Beispielkonto für den lokalen Test:

- Benutzer: `admin`
- Passwort: `ParkPilotLocal2026!`

Drei Testfahrzeuge werden beim ersten Start angelegt. Das Passwort kann in der App geändert werden. Ein später geändertes `ADMIN_PASSWORD` in `.env` setzt ein vorhandenes Passwort nicht zurück.

Für das Aktualisieren einer bereits laufenden Installation siehe **AKTUALISIERUNG.md**. Dabei die vorhandene `.env` behalten und im bisherigen Projektordner bleiben.

## Funktionen

- Fahrzeugübersicht mit Kennzeichen, Modell, Fahrzeugtyp, Kilometerstand, Bemerkungen und aktuellem Zustand.
- Eigene Fahrzeugtypen in der Admin-Konsole erstellen, umbenennen und beschreiben; Fahrzeuge in der App einem Typ zuordnen.
- Fahrzeuge und Verfügbarkeit nach Typ filtern.
- Zeitraum von/bis suchen und ein freies Fahrzeug direkt mit diesen Zeiten reservieren.
- Ausgabe und Rückgabe mit Benutzer, tatsächlichen Zeitpunkten, geplanter Rückgabe, Kilometerstand, Zweck und Rückgabehinweis.
- Reservierungen erstellen, stornieren und im reservierten Zeitfenster übernehmen.
- Monatskalender für Reservierungen und Nutzungen, mit Monatswechsel und Fahrzeug-/Typfilter.
- Mehrtägige Kalendereinträge an allen betroffenen Tagen; Details durch Anklicken.
- Allgemeiner Reservierungs-QR-Code und individuelle Fahrzeug-QR-Codes; herunterladen und drucken.
- Persönliche Anmeldung, Passwortwechsel und Rollen.
- Nutzungshistorie mit CSV-Export sowie Änderungsprotokoll.
- Schutz gegen Buchungskonflikte, doppelte Ausgabe/Rückgabe und veraltete Fahrzeugänderungen.
- Deutsche Oberfläche; Zeiten in Europe/Zurich, Speicherung in UTC.
- Gemeinsame Datenbank im persistenten Docker-Volume; automatische Übersichtsaktualisierung alle 30 Sekunden.

Parkplatznummern werden in der Oberfläche und den Eingabeformularen nicht mehr verwendet.

## Rollen und Benutzer

Als Administrator links „Benutzer verwalten“ öffnen und persönliche Konten anlegen. Die beiden Berechtigungsfelder bestimmen die Rolle:

| Rolle | Einstellungen | Rechte |
|---|---|---|
| Mitarbeitende | Aktiv; kein Mitarbeiterstatus, kein Superuser | Übersicht, Kalender und Historie lesen; QR-Codes öffnen; eigene Reservierung, Ausgabe und Rückgabe |
| Disposition | Aktiv + Mitarbeiterstatus (`is_staff`) | Zusätzlich für andere handeln, Fahrzeuge verwalten und Änderungsprotokoll lesen |
| Administrator | Aktiv + Mitarbeiterstatus + Superuser | Zusätzlich Benutzer und Fahrzeugtypen in der Admin-Konsole verwalten |

„Mitarbeiterstatus“ steht in dieser App für Disposition. Alle angemeldeten Benutzer sehen die gemeinsame Historie und die Kalenderbuchungen, inklusive Namen und Hinweisen.

Fahrzeuge und Buchungen sind in der Django-Administration nur lesbar registriert. Änderungen daran erfolgen über die App. Fahrzeugtypen sind in der Administration bearbeitbar. Referenzierte Typen können nicht gelöscht werden, solange Fahrzeuge sie verwenden.

## Fahrzeugtypen definieren

1. Als Administrator anmelden.
2. „Fahrzeugtypen verwalten“ öffnen: `http://localhost:8080/admin/fleet/vehicletype/`.
3. „Fahrzeugtyp hinzufügen“ wählen, z. B. Personenwagen, Lieferwagen oder Geländewagen.
4. Optional Beschreibung eingeben und speichern.
5. In der Fahrzeugübersicht „Bearbeiten“ öffnen und den Typ auswählen.

Bestehende Fahrzeuge bleiben beim Update erhalten und haben zunächst „Ohne Typ“. Die Zuordnung ist optional. Bei einer frischen Demo-Installation werden Personenwagen und Transporter als Beispieltypen angelegt.

## Verfügbarkeit suchen

„Verfügbarkeit suchen“ öffnen, Datum und Uhrzeit für Von und Bis eingeben, optional Typ auswählen und suchen. Die Ergebnisliste enthält nur aktive Fahrzeuge, die im gesamten Intervall nach den aktuellen Buchungen verfügbar sind.

„Für diesen Zeitraum reservieren“ übernimmt die Zeiten in das Formular. Benutzer und Zweck wählen und speichern. Beim Speichern wird die Verfügbarkeit erneut innerhalb einer gesperrten Datenbanktransaktion geprüft.

Eine aktuelle Nutzung blockiert bis zur geplanten Rückgabe. Verfügbarkeit nach einer solchen Rückgabe wird entsprechend gekennzeichnet. Bei einer bereits überfälligen Rückgabe wird das Fahrzeug bis zur tatsächlichen Rückgabe nicht angeboten.

## Buchungskalender

`http://localhost:8080/calendar/` zeigt den aktuellen Monat. Monat, Fahrzeugtyp oder ein bestimmtes Fahrzeug auswählen und „Anzeigen“ klicken. Monatswechsel behalten die Filter bei.

- Gelb: Reservierung.
- Blau: tatsächliche oder aktuell laufende Nutzung.
- Rot: laufende Nutzung mit überfälliger Rückgabe; Ende noch offen.

Auf eine Buchung klicken, um Fahrzeugtyp, Benutzer, Zeiten und Zweck zu sehen. Mehrtägige Buchungen erscheinen an jedem betroffenen Tag. Ein Ende exakt um 00:00 belegt den anschliessenden Tag nicht. Stornierte Reservierungen werden ausgeblendet. Übernommene Reservierungen werden durch die zugehörige Nutzung dargestellt.

Bei einer überfälligen Nutzung zeigen spätere Kalendertage „Rückgabe offen“. Das ist ein Hinweis auf die blockierte Verfügbarkeit, kein verbindlich geplanter Rückgabezeitpunkt. Auf kleinen Bildschirmen kann der Monatskalender horizontal gescrollt werden.

## QR-Codes zum Reservieren

`http://localhost:8080/qr/` oder links „Reservieren per QR-Code“ öffnen. Der allgemeine Code führt zur Verfügbarkeitssuche. In jeder Fahrzeugzeile öffnet „QR-Code“ einen individuellen Code für die Reservierung dieses Fahrzeugs.

Der Code lässt sich als SVG herunterladen und drucken. Er enthält einen Link, keine Passwörter oder Zugangstoken. Nach dem Scannen ist die persönliche Anmeldung erforderlich, danach öffnet sich die Reservierungsseite.

**Für ein Handy funktioniert localhost nicht.** Handy und Server-PC müssen dieselbe erreichbare Netzwerkadresse verwenden. Beispiel für die LAN-IP des PCs `192.168.1.50`: vorhandene `.env` anpassen:

```dotenv
BIND_ADDRESS=0.0.0.0
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
CSRF_TRUSTED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://192.168.1.50:8080
PUBLIC_BASE_URL=http://192.168.1.50:8080
```

Die Beispiel-IP durch deine tatsächliche LAN-IP ersetzen. Unter Windows mit `ipconfig` die IPv4-Adresse der aktiven WLAN-/Ethernet-Verbindung ermitteln. Nicht eine Docker-/WSL-Netzwerkadresse verwenden.

Dann `docker compose up --build -d`. Handy ins gleiche WLAN verbinden und zuerst `http://DEINE-IP:8080` im Handy-Browser öffnen. Falls nötig TCP-Port 8080 in der Windows-Firewall im privaten Netzwerk erlauben. Erst wenn die Adresse im Handy-Browser erreichbar ist, den QR-Code scannen.

`PUBLIC_BASE_URL` enthält Protokoll, Host und optional Port, keinen weiteren Pfad. Bleibt sie leer, wird die Adresse der aktuellen Browseranfrage verwendet. Wenn dies localhost ist, zeigt die QR-Seite einen entsprechenden Hinweis. Wird die LAN-IP geändert, muss PUBLIC_BASE_URL angepasst und ein gedruckter QR-Code neu erstellt werden. Für gedruckte Codes ist eine gleichbleibende LAN-Adresse sinnvoll.

## Start, Stop, Tests

```powershell
# Status und Logs
docker compose ps
docker compose logs --tail=100 web

# Stoppen, Daten bleiben erhalten
docker compose down

# Starten / Code neu bauen
docker compose up --build -d

# Konto-Passwort interaktiv ändern
docker compose exec web python manage.py changepassword admin

# Prüfungen
docker compose exec web python manage.py check
docker compose exec web python manage.py makemigrations --check --dry-run
docker compose exec web python manage.py test --verbosity 2
```

Der Web-Start führt Migrationen, Initialisierung und `collectstatic` automatisch aus. Die Tests verwenden eine separate temporäre Datenbank; der lokale Standardbenutzer kann diese anlegen. Erwartung mit PostgreSQL: alle 58 Tests erfolgreich. Tatsächlich durchgeführte Prüfungen stehen in `docs/TESTBERICHT.md`.

**`docker compose down -v` löscht die Datenbankdaten** und ist nur für einen bewusst gewünschten vollständigen Testreset geeignet. `SEED_DEMO=0` verhindert beim ersten Start Testfahrzeuge; vorhandene Fahrzeuge werden dadurch nicht entfernt.

## Sicherung und Wiederherstellung

Die PowerShell-Skripte nutzen die PostgreSQL-Werkzeuge im Container. Keine Binärdaten laufen durch eine PowerShell-Pipeline:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\backup.ps1 -Destination .\parking.dump
powershell -ExecutionPolicy Bypass -File .\scripts\restore.ps1 -Source .\parking.dump
```

Die Wiederherstellung ersetzt den Datenbankstand durch die Sicherung. Währenddessen wird die Web-App angehalten. Eigene Datenbanknamen und Benutzer aus `.env` werden unterstützt.

## Mehrere Windows-PCs

Nur ein Server-PC startet den Compose-Stack. Alle anderen Geräte öffnen seine LAN-Adresse im Browser; sie starten keine eigene Datenbank. Die Netzwerkkonfiguration entspricht der QR-Code-Konfiguration oben. PostgreSQL hat keinen veröffentlichten Port.

Die Beispielkonfiguration dient dem lokalen Test mit HTTP. Für dauerhaften Betrieb oder Internetzugriff sind eigene Zugangsdaten, HTTPS und geregelte Sicherungen erforderlich.

## Entwicklung ohne Docker

Python 3.12 und eine virtuelle Umgebung verwenden. `.env` wird ausserhalb von Docker nicht automatisch gelesen:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:USE_SQLITE="1"
$env:DEBUG="1"
$env:ADMIN_PASSWORD="ParkPilotLocal2026!"
$env:SEED_DEMO="1"
python manage.py migrate
python manage.py bootstrap
python manage.py collectstatic --noinput
python manage.py runserver
```

Entwicklung unter `http://127.0.0.1:8000`. SQLite prüft keine PostgreSQL-Zeilensperren; Mehrbenutzerbetrieb erfolgt mit PostgreSQL.

## Fachliche Regeln

- Reservierungsintervalle `[Start, Ende)`; direkt anschliessende Buchungen sind erlaubt.
- Ausgabe benötigt eine geplante Rückgabe und einen überschneidungsfreien Zeitraum.
- Eine aktuelle eigene Reservierung über „Übernehmen“ mit der Nutzung verknüpfen.
- Nur eine offene Nutzung pro Fahrzeug; doppelte Rückgaben werden abgewiesen.
- Verspätete Rückgaben können bestehende spätere Reservierungen beeinträchtigen. Bis zur Rückgabe ist keine neue Ausgabe möglich.
- Kilometerstände dürfen nicht sinken.
- Fahrzeuge in Betrieb werden erst nach Rückgabe bearbeitet. Vor dem Deaktivieren müssen anstehende Reservierungen storniert werden.
- Fahrzeugformulare führen eine Versionsnummer mit, um neuere Änderungen nicht zu überschreiben.
- Reservierungen werden zur Änderung storniert und neu angelegt.

## Vollständige Ordnerstruktur

```text
parkplatzverwaltung/
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── docs/
│   ├── ARCHITEKTUR.md
│   └── TESTBERICHT.md
├── fleet/
│   ├── management/
│   │   ├── commands/
│   │   │   ├── __init__.py
│   │   │   └── bootstrap.py
│   │   └── __init__.py
│   ├── migrations/
│   │   ├── 0001_initial.py
│   │   ├── 0002_vehicletype_vehicle_vehicle_type.py
│   │   └── __init__.py
│   ├── __init__.py
│   ├── admin.py
│   ├── calendar.py
│   ├── forms.py
│   ├── models.py
│   ├── qr.py
│   ├── services.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── scripts/
│   ├── backup.ps1
│   ├── entrypoint.sh
│   └── restore.ps1
├── static/
│   └── fleet/
│       ├── app.css
│       └── app.js
├── templates/
│   ├── fleet/
│   │   ├── audit.html
│   │   ├── availability.html
│   │   ├── calendar.html
│   │   ├── dashboard.html
│   │   ├── form.html
│   │   ├── history.html
│   │   ├── pagination.html
│   │   ├── qr.html
│   │   └── reservations.html
│   ├── registration/
│   │   ├── login.html
│   │   └── password_change_done.html
│   ├── 403.html
│   ├── 404.html
│   ├── 500.html
│   └── base.html
├── .dockerignore
├── .env.example
├── .gitattributes
├── .gitignore
├── AKTUALISIERUNG.md
├── Dockerfile
├── LICENSE
├── README.md
├── compose.yaml
├── manage.py
└── requirements.txt
```
