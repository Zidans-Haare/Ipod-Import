#!/bin/bash
# iPod Manager – Einmaliger Installer für macOS
set -e

echo "=== iPod Manager Setup ==="
echo ""

# Check Python 3
if ! command -v python3 &>/dev/null; then
  echo "FEHLER: Python 3 nicht gefunden."
  echo "Bitte Python 3 von https://python.org herunterladen."
  read -p "Drücke Enter zum Beenden…"
  exit 1
fi
echo "✓ Python $(python3 --version)"

# Install Python packages
echo ""
echo "Installiere Python-Pakete (mutagen, yt-dlp)…"
python3 -m pip install --break-system-packages --quiet mutagen yt-dlp 2>/dev/null \
  || python3 -m pip install --quiet mutagen yt-dlp
echo "✓ Python-Pakete installiert"

# Check / install ffmpeg via Homebrew
echo ""
if command -v ffmpeg &>/dev/null; then
  echo "✓ ffmpeg gefunden"
elif command -v brew &>/dev/null; then
  echo "Installiere ffmpeg via Homebrew…"
  brew install ffmpeg
  echo "✓ ffmpeg installiert"
else
  echo "⚠  ffmpeg nicht gefunden."
  echo "   Für YouTube-Downloads: Homebrew installieren (brew.sh) und dann 'brew install ffmpeg' ausführen."
fi

echo ""
echo "=== Setup abgeschlossen! ==="
echo ""
echo "App starten: Doppelklick auf 'start.command'"
echo "         oder: python3 main.py"
echo ""
read -p "Drücke Enter zum Beenden…"
