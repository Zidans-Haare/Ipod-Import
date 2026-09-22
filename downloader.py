"""YouTube audio download using yt-dlp Python API (no subprocess needed)."""

import os
import shutil


def check_tool(name: str) -> bool:
    if name == "yt-dlp":
        try:
            import yt_dlp  # noqa: F401
            return True
        except ImportError:
            return shutil.which("yt-dlp") is not None
    return shutil.which(name) is not None


def get_video_info(url: str) -> dict:
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
            return ydl.extract_info(url, download=False) or {}
    except ImportError:
        raise RuntimeError("yt-dlp nicht installiert.")


def download_audio(url: str, out_dir: str, progress_cb=None) -> str:
    """Download best audio into out_dir. Returns path to downloaded file."""

    def _cb(msg, pct):
        if progress_cb:
            progress_cb(msg, pct)

    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp nicht installiert. Bitte 'pip3 install yt-dlp' ausführen.")

    downloaded = []

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done  = d.get("downloaded_bytes", 0)
            pct   = (done / total * 70 + 10) if total else 30
            speed = d.get("_speed_str", "")
            _cb(f"Lade herunter… {speed}", pct)
        elif d["status"] == "finished":
            downloaded.append(d["filename"])
            _cb("Verarbeite Audio…", 85)

    _cb("Verbinde mit YouTube…", 5)

    ffmpeg_ok = shutil.which("ffmpeg") is not None

    if ffmpeg_ok:
        fmt = "bestaudio/best"
        postprocessors = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "m4a",
            "preferredquality": "192",
        }]
    else:
        fmt = "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio"
        postprocessors = []

    opts = {
        "format": fmt,
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "postprocessors": postprocessors,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    info = {}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True) or {}

    # Build metadata from yt-dlp info dict (music videos often have artist/track fields)
    meta = {
        "title":  info.get("track")  or info.get("title", ""),
        "artist": info.get("artist") or info.get("creator") or info.get("uploader", ""),
        "album":  info.get("album",  ""),
    }

    # Find the downloaded file — check for ffmpeg-converted extension first
    found = None
    if downloaded:
        path = downloaded[-1]
        base = os.path.splitext(path)[0]
        for ext in (".m4a", ".mp3", ".aac", ".webm", ".opus", ".ogg"):
            if os.path.exists(base + ext):
                found = base + ext
                break
        if not found and os.path.exists(path):
            found = path

    if not found:
        for f in sorted(os.listdir(out_dir)):
            if f.endswith((".m4a", ".mp3", ".webm", ".opus", ".ogg", ".aac")):
                found = os.path.join(out_dir, f)
                break

    if not found:
        raise RuntimeError("Download fehlgeschlagen — keine Audiodatei gefunden.")

    # Remux DASH/fragmented M4A to standard M4A so iPod classic can play it
    if ffmpeg_ok and found.endswith(".m4a"):
        with open(found, "rb") as f:
            magic = f.read(16)
        if b"dash" in magic or b"webm" in magic:
            import subprocess
            tmp = found + ".ipod.m4a"
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", found, "-c:a", "aac", "-b:a", "192k", tmp],
                capture_output=True,
            )
            if r.returncode == 0 and os.path.exists(tmp):
                os.replace(tmp, found)

    return found, meta
