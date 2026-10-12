# Update: Fahrzeugtypen, Buchungskalender und QR-Codes

## Vorhandene Installation aktualisieren

1. Neues ZIP separat entpacken.
2. Den **Inhalt** von `parkplatzverwaltung` in deinen bisherigen Projektordner, z. B. `pp_militaer`, kopieren und Quelldateien ersetzen.
3. Deine vorhandene `.env` behalten. `.env.example` nicht darüberkopieren.
4. Im VS-Code-Terminal **im bisherigen Projektordner** ausführen:

```powershell
docker compose up --build -d
docker compose ps
```

Die neue Migration `0002_vehicletype_vehicle_vehicle_type.py` läuft beim Start automatisch. Sie ergänzt Fahrzeugtypen und deren Zuordnung. Bestehende Fahrzeuge, Konten, Reservierungen und Nutzungen bleiben erhalten. Parkplatznummern sind aus den Formularen und Ansichten entfernt; alte Werte werden intern für die Datenverträglichkeit aufbewahrt.

Der bisherige Projektordner ist wichtig: Docker Compose leitet daraus den Projektnamen und das Datenbank-Volume ab. Nicht aus einem neuen Updateordner einen zweiten Stack starten. `docker compose down -v` nicht zum Aktualisieren verwenden.

## Fahrzeugtypen definieren

Als Administrator „Fahrzeugtypen verwalten“ öffnen oder:

`http://localhost:8080/admin/fleet/vehicletype/`

Eigene Typen hinzufügen, dann bei jedem Fahrzeug über „Bearbeiten“ den passenden Typ auswählen. Vorhandene Fahrzeuge ohne Zuordnung werden als „Ohne Typ“ angezeigt.

## Kalender

`http://localhost:8080/calendar/`

Monat auswählen, optional nach Typ/Fahrzeug filtern. Auf Einträge klicken, um Benutzer, Zeitraum und Zweck zu sehen. Gelb = Reservierung, Blau = Nutzung, Rot = Rückgabe noch offen. Stornierungen werden ausgeblendet.

## QR-Code für dein Handy einrichten

1. Im Windows-Terminal `ipconfig` ausführen und die IPv4-Adresse deiner aktiven WLAN-/Ethernet-Verbindung ermitteln.
2. In der vorhandenen `.env` folgende Werte anpassen/ergänzen. **192.168.1.50 durch deine tatsächliche IP ersetzen**:

```dotenv
BIND_ADDRESS=0.0.0.0
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50
CSRF_TRUSTED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080,http://192.168.1.50:8080
PUBLIC_BASE_URL=http://192.168.1.50:8080
```

3. `docker compose up --build -d` ausführen.
4. Handy ins gleiche WLAN verbinden und die Adresse zuerst im Handy-Browser testen: `http://DEINE-IP:8080`. Bei Bedarf Port 8080 im privaten Netzwerk in der Windows-Firewall freigeben.
5. Am PC `http://localhost:8080/qr/` öffnen. QR-Code scannen, als SVG speichern oder drucken.

Der allgemeine QR-Code öffnet die Fahrzeugsuche. Über „QR-Code“ in einer Fahrzeugzeile kannst du einen individuellen Code für genau dieses Fahrzeug ausdrucken. Auch nach dem Scannen ist eine persönliche Anmeldung erforderlich. Der Code enthält keine Zugangsdaten.

## Änderungen für lokale Eigenanpassungen

```text
config/settings.py
config/urls.py
.env.example
requirements.txt
fleet/models.py
fleet/admin.py
fleet/forms.py
fleet/services.py
fleet/views.py
fleet/urls.py
fleet/calendar.py                                  (neu)
fleet/qr.py                                        (neu)
fleet/tests.py
fleet/management/commands/bootstrap.py
fleet/migrations/0002_vehicletype_vehicle_vehicle_type.py (neu)
templates/base.html
templates/fleet/dashboard.html
templates/fleet/availability.html
templates/fleet/calendar.html                      (neu)
templates/fleet/qr.html                            (neu)
static/fleet/app.css
static/fleet/app.js
README.md
AKTUALISIERUNG.md
docs/ARCHITEKTUR.md
docs/TESTBERICHT.md
```

Wenn du lokal eigene Änderungen vorgenommen hast, die Dateien vergleichen und gezielt übernehmen. Docker neu bauen, damit die QR-Code-Abhängigkeit installiert wird. Die UI benötigt keine externen Kalender- oder QR-Code-Dienste.

## Tests

```powershell
docker compose exec web python manage.py test --verbosity 2
```

Mit PostgreSQL sollten alle 58 Tests laufen. Der Erstellungsumgebung fehlte Docker/PostgreSQL; dort wurden 55 Tests erfolgreich und drei PostgreSQL-Tests übersprungen.
