# Architektur

## Aufbau

Windows-/Handy-Browser → HTTP Port 8080 → Gunicorn / Django → PostgreSQL.

Compose enthält `web` und `db`. Django rendert serverseitige HTML-Templates. WhiteNoise liefert lokale CSS-/JavaScript-Dateien, Gunicorn bearbeitet Anfragen in drei Prozessen. Das PostgreSQL-Volume enthält die gemeinsame Datenbasis. Formulare sind durch Sitzungsanmeldung und CSRF geschützt.

Kalender und QR-Codes benötigen keine externen Dienste: Der Kalender wird in Python aufgebaut und als HTML gerendert; `qrcode` erstellt SVG-Dateien direkt auf dem Server.

## Datenmodell

| Modell | Zweck |
|---|---|
| Django User | Konto, Passwort-Hash, Name und Rolle |
| VehicleType | Selbst definierbare Typbezeichnung und Beschreibung |
| Vehicle | Kennzeichen, Modell, optional Typ, Kilometerstand, Bemerkungen, Aktivierung und Version |
| Reservation | Fahrzeug, Nutzer, Start/Ende, Zweck, Status, Ersteller |
| Usage | Fahrer, tatsächlicher Start, geplante/tatsächliche Rückgabe, Kilometerstände, erfassende Benutzer und optional Reservierung |
| Audit | Benutzer, Fahrzeug, Zeitpunkt, Aktion, Details |

Historische Fremdschlüssel verwenden `PROTECT`. Fahrzeugtypen können nicht gelöscht werden, solange sie referenziert werden. Alte Fahrzeuge dürfen untypisiert bleiben. Die Migration ergänzt Schema, ohne bestehende Datensätze zu entfernen.

Das alte `Vehicle.space` bleibt als nicht mehr in der Oberfläche verwendetes Legacy-Feld bestehen. So verliert eine bestehende Installation bei diesem Update keine gespeicherten Werte. Neue Ausgabe-/Rückgabeformulare verarbeiten keine Parkplatznummern.

## Zuständigkeiten

- `models.py`: Schema und Constraints.
- `forms.py`: Eingaben, Typauswahl, Zeiträume, Monatsfilter und Nutzer.
- `services.py`: Rechte, fachliche Regeln, Verfügbarkeit, Transaktionen und Audit.
- `calendar.py`: Monatsraster in Schweizer Zeit, inklusive mehrtägiger Intervalle und Sommerzeit.
- `qr.py`: Zieladresse mit optionaler PUBLIC_BASE_URL.
- `views.py`: Listen, Formulare, Kalender und QR-Auslieferung.
- `admin.py`: Bearbeitbare Fahrzeugtypen; Fahrzeuge/Buchungen/Audit nur lesbar.
- `bootstrap`: Idempotente Einrichtung. Bei neuen Testfahrzeugen werden Beispieltypen angelegt; vorhandene Fahrzeuge und Passwörter werden nicht überschrieben.

## Gleichzeitige Änderungen

Alle Buchungs-, Ausgabe-, Rückgabe- und Fahrzeugänderungen sperren dieselbe Fahrzeugzeile innerhalb von `transaction.atomic()` mit `select_for_update()`. Wartende Transaktionen prüfen danach den aktuellen Zustand. Audit und Änderung werden gemeinsam geschrieben oder zurückgerollt.

Stornierung und Rückgabe lesen den Buchungsdatensatz nach Erwerb der Fahrzeugzeilensperre erneut. Die Datenbank erzwingt zusätzlich eine offene Nutzung je Fahrzeug, ein positives Reservierungsintervall und nicht sinkende Nutzungskilometerstände.

Reservierungsüberschneidungen werden unter Fahrzeugzeilensperre geprüft. Direktes SQL an den Services vorbei ist kein unterstützter Buchungsweg. Suchergebnisse sind Momentaufnahmen; eine anschliessende Reservierung prüft den Zustand erneut.

Fahrzeugformulare verwenden Versionsnummern. Ausgabe und Rückgabe erhöhen dieselbe Versionsnummer, sodass alte Formulare neuere Änderungen nicht überschreiben.

## Kalenderregeln

Das sichtbare Monatsraster startet montags und umfasst bei Bedarf Randtage aus Nachbarmonaten. Die Abfragen berücksichtigen den gesamten Rasterzeitraum. Reservierungen verwenden exklusive Enden: ein Ende um Mitternacht belegt den Folgetag nicht. Tagesgrenzen werden separat in Europe/Zurich gebildet, damit Tage mit Sommerzeitwechsel korrekt sind.

Stornierungen werden ausgelassen. Nach Übernahme erscheint die zugehörige Nutzung statt einer doppelten Reservierung. Rückgaben begrenzen Nutzungen auf den tatsächlichen Zeitraum. Überfällige offene Nutzungen werden bis zum Ende des sichtbaren Rasters als „Rückgabe offen“ gekennzeichnet.

## QR-Adresse und Anmeldung

PUBLIC_BASE_URL ist eine optionale feste HTTP-/HTTPS-Basisadresse ohne Pfad, Zugangsdaten, Query oder Fragment. Ohne Konfiguration wird die Adresse der Browseranfrage verwendet. Ein localhost-Ziel zeigt einen Hinweis, da Handys den Server darüber nicht erreichen können.

Der allgemeine Code führt zu `/availability/`, der Fahrzeugcode zu `/vehicles/ID/reserve/`. Der Link umgeht keine Anmeldung. Django behält den Zielpfad über den Login bei. SVG-Erzeugung erfolgt nur für angemeldete Benutzer; der Code enthält keine Sitzungsdaten. Die QR-Auslieferung verwendet keinen gemeinsamen Cache.

## Grenzen

Keine Sensorerkennung, automatische Kennzeichenerkennung, Benachrichtigungen, Buchungsserien oder native mobile App. Reservierungsänderungen erfolgen durch Stornieren und Neuanlegen. QR-Reservierung am Handy benötigt eine erreichbare Netzwerkadresse und ein Benutzerkonto. Die lokale HTTP-Konfiguration ist keine vollständige Internetbereitstellung mit HTTPS/SSO.

## Technische Dokumentation

- [Django: Transaktionen](https://docs.djangoproject.com/en/5.2/topics/db/transactions/)
- [Django: select_for_update](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update)
- [Docker Compose: Startreihenfolge](https://docs.docker.com/compose/how-tos/startup-order/)
- [python-qrcode: SVG-Erzeugung](https://github.com/lincolnloop/python-qrcode)
