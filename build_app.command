#!/bin/bash
# Baut die iPod Manager.app — einmal ausführen, dann fertig.
cd "$(dirname "$0")"

echo "=== iPod Manager — App bauen ==="
echo ""

if ! command -v python3 &>/dev/null; then
  echo "FEHLER: Python 3 nicht gefunden."
  echo "Bitte von https://python.org herunterladen."
  read -p "Enter drücken zum Beenden…"
  exit 1
fi

echo "Installiere Pakete…"
python3 -m pip install --break-system-packages --quiet \
  customtkinter mutagen yt-dlp pyinstaller 2>/dev/null \
  || python3 -m pip install --quiet \
  customtkinter mutagen yt-dlp pyinstaller

CTK_PATH=$(python3 -c "import os,customtkinter; print(os.path.dirname(customtkinter.__file__))")
echo "customtkinter: $CTK_PATH"

echo ""
echo "Baue .app (dauert ~1–2 Minuten)…"
python3 -m PyInstaller --noconfirm \
  --windowed \
  --name "iPod Manager" \
  --add-data "$CTK_PATH:customtkinter" \
  --hidden-import customtkinter \
  --hidden-import mutagen \
  --hidden-import mutagen.mp4 \
  --hidden-import mutagen.mp3 \
  --hidden-import mutagen.id3 \
  main.py

if [ -d "dist/iPod Manager.app" ]; then
  echo ""
  echo "✅  Fertig! Die App liegt in:"
  echo "    $(pwd)/dist/iPod Manager.app"
  echo ""
  echo "Einfach in den Programme-Ordner kopieren und doppelklicken."
  open dist/
else
  echo "❌  Build fehlgeschlagen — siehe Fehlermeldung oben."
fi

echo ""
read -p "Enter drücken zum Beenden…"
