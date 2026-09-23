# iPod Manager

Einfache Desktop-App zum Verwalten eines klassischen iPods (iPod Nano, Classic, Mini).

## Funktionen

- **Bibliothek anzeigen** — alle Tracks mit Titel, Künstler, Album, Dauer und Dateigröße
- **Musik hinzufügen** — M4A / MP3 / AAC-Dateien direkt vom Computer laden
- **YouTube Import** — URL eingeben → Audio herunterladen → automatisch auf iPod laden
- **Track löschen** — ausgewählten Song sicher entfernen (mit Bestätigung)
- **iPod auswerfen** — sicheres Trennen per Knopf

## Installation (Mac)

### Fertiger Download (empfohlen)

1. `iPod_Manager_mac_v1.2.zip` herunterladen und entpacken
2. `iPod Manager.app` in den Programme-Ordner ziehen
3. **Erstes Öffnen:** Rechtsklick auf die App → **Öffnen** → im Dialog nochmal **Öffnen** klicken  
   *(macOS blockiert Apps aus dem Internet beim ersten Start — danach geht Doppelklick normal)*

### Aus dem Quellcode starten

1. Diesen Ordner irgendwo auf dem Computer speichern
2. `build_app.command` doppelklicken — baut die App automatisch

**Hinweis:** Falls macOS meldet „konnte nicht überprüft werden, ob die Datei beschädigt ist":
```
xattr -cr build_app.command
```
im Terminal eingeben (du musst vorher `cd` in den Ordner machen), danach klappt der Doppelklick.

**Voraussetzungen:** Python 3 (von python.org)

## App starten

```bash
python3 main.py
```

oder Doppelklick auf `start.command`.

## YouTube-Downloads

Erfordert `yt-dlp` und `ffmpeg` (werden durch `setup.sh` installiert).  
URL aus dem Browser kopieren und in das URL-Feld einfügen.

## Hinweis

Die App sichert die iPod-Datenbank automatisch als `iTunesDB.bak` vor jeder Änderung.
