# iPod Manager

Einfache Desktop-App zum Verwalten eines klassischen iPods (iPod Nano, Classic, Mini).

## Funktionen

- **Bibliothek anzeigen** — alle Tracks mit Titel, Künstler, Album, Dauer und Dateigröße
- **Musik hinzufügen** — M4A / MP3 / AAC-Dateien direkt vom Computer laden
- **YouTube Import** — URL eingeben → Audio herunterladen → automatisch auf iPod laden
- **Track löschen** — ausgewählten Song sicher entfernen (mit Bestätigung)
- **iPod auswerfen** — sicheres Trennen per Knopf

## Installation (Mac)

1. Diesen Ordner irgendwo auf dem Computer speichern
2. `setup.command` doppelklicken — installiert alles automatisch
3. Danach: `start.command` doppelklicken zum Starten

**Voraussetzungen:** Python 3 (von python.org), Homebrew (für ffmpeg/YouTube)

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
