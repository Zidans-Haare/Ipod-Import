"""YouTube audio download using yt-dlp."""

import os
import re
import subprocess
import tempfile


def check_tool(name):
    try:
        subprocess.run([name, "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_video_info(url):
    """Return dict with title/duration/uploader, or None on failure."""
    try:
        r = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print",
             "%(title)s\n%(duration)s\n%(uploader)s", url],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            parts = r.stdout.strip().split("\n")
            try:
                dur = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                dur = 0
            return {
                "title": parts[0] if parts else url,
                "duration": dur,
                "uploader": parts[2] if len(parts) > 2 else "",
            }
    except Exception:
        pass
    return None


def download_audio(url, out_dir, progress_cb=None):
    """Download and extract audio as m4a. Returns path to output file."""
    def _cb(msg, pct):
        if progress_cb:
            progress_cb(msg, pct)

    _cb("Starte Download…", 5)

    tpl = os.path.join(out_dir, "%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-x",
        "--audio-format", "m4a",
        "--audio-quality", "0",
        "-o", tpl,
        "--newline",
        url,
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    output_file = None

    for line in proc.stdout:
        line = line.strip()
        if "[download]" in line and "%" in line:
            m = re.search(r"(\d+\.?\d*)%", line)
            if m:
                pct = float(m.group(1))
                _cb(f"Herunterladen… {pct:.0f}%", int(5 + pct * 0.75))
        elif "Destination:" in line:
            output_file = line.split("Destination:", 1)[-1].strip()
            _cb("Konvertiere Audio…", 85)

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("yt-dlp fehlgeschlagen — URL überprüfen")

    # Fall back: find newest audio file in out_dir
    if not output_file or not os.path.exists(output_file):
        candidates = [
            (os.path.getmtime(os.path.join(out_dir, f)),
             os.path.join(out_dir, f))
            for f in os.listdir(out_dir)
            if f.lower().endswith((".m4a", ".mp4", ".aac", ".mp3", ".webm"))
        ]
        if candidates:
            output_file = sorted(candidates, reverse=True)[0][1]

    if not output_file or not os.path.exists(output_file):
        raise RuntimeError("Ausgabedatei nicht gefunden")

    _cb("Download abgeschlossen!", 100)
    return output_file
