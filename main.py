"""iPod Manager — GUI application."""

import os
import sys
import threading
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from ipod_db import find_ipod, ipod_name, iPodDB
import downloader

APP_TITLE  = "iPod Manager"
APP_WIDTH  = 900
APP_HEIGHT = 620
ACCENT     = "#007AFF"
BG         = "#f5f5f7"
SIDEBAR_BG = "#e8e8ed"
ROW_ODD    = "#ffffff"
ROW_EVEN   = "#f0f0f5"


def fmt_duration(ms):
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def fmt_size(b):
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} MB"
    return f"{b // 1000} KB"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.resizable(True, True)
        self.configure(bg=BG)

        self.ipod_path = None
        self.db: iPodDB | None = None
        self.tracks = []
        self._dl_thread = None

        self._build_ui()
        self._auto_connect()

    # ----------------------------------------------------------------- UI build
    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=SIDEBAR_BG, height=44)
        top.pack(side=tk.TOP, fill=tk.X)
        top.pack_propagate(False)

        self._lbl_status = tk.Label(top, text="Kein iPod verbunden",
                                    bg=SIDEBAR_BG, fg="#555",
                                    font=("Helvetica", 13, "bold"))
        self._lbl_status.pack(side=tk.LEFT, padx=16, pady=10)

        self._btn_refresh = tk.Button(top, text="⟳ Aktualisieren",
                                      command=self._reload,
                                      bg=ACCENT, fg="white",
                                      relief=tk.FLAT, padx=10, pady=4,
                                      cursor="hand2",
                                      font=("Helvetica", 11))
        self._btn_refresh.pack(side=tk.RIGHT, padx=8, pady=8)

        self._btn_eject = tk.Button(top, text="⏏ Auswerfen",
                                    command=self._eject,
                                    bg="#555", fg="white",
                                    relief=tk.FLAT, padx=10, pady=4,
                                    cursor="hand2",
                                    font=("Helvetica", 11))
        self._btn_eject.pack(side=tk.RIGHT, padx=4, pady=8)

        # ── Main area: left track list + right panel ──────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)

        # Left: track list
        left = tk.Frame(body, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 4), pady=8)

        self._lbl_count = tk.Label(left, text="Tracks (0)",
                                   bg=BG, fg="#333",
                                   font=("Helvetica", 12))
        self._lbl_count.pack(anchor=tk.W, pady=(0, 4))

        cols = ("Titel", "Künstler", "Album", "Dauer", "Größe")
        self._tree = ttk.Treeview(left, columns=cols, show="headings",
                                   selectmode="browse")
        widths = (260, 160, 160, 60, 70)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=w, minwidth=40)

        vsb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._tree.tag_configure("odd",  background=ROW_ODD)
        self._tree.tag_configure("even", background=ROW_EVEN)

        # Right: actions panel (fixed width)
        right = tk.Frame(body, bg=SIDEBAR_BG, width=220)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 12), pady=8)
        right.pack_propagate(False)

        self._build_actions(right)

        # ── Bottom: progress bar + status ────────────────────────────────
        bot = tk.Frame(self, bg=SIDEBAR_BG, height=36)
        bot.pack(side=tk.BOTTOM, fill=tk.X)
        bot.pack_propagate(False)

        self._pb = ttk.Progressbar(bot, length=220, mode="determinate")
        self._pb.pack(side=tk.LEFT, padx=12, pady=8)

        self._lbl_progress = tk.Label(bot, text="",
                                      bg=SIDEBAR_BG, fg="#555",
                                      font=("Helvetica", 10))
        self._lbl_progress.pack(side=tk.LEFT, padx=6)

    def _build_actions(self, parent):
        pad = dict(padx=10, pady=5, fill=tk.X)

        tk.Label(parent, text="Musik hinzufügen",
                 bg=SIDEBAR_BG, fg="#222",
                 font=("Helvetica", 12, "bold")).pack(anchor=tk.W, **pad)

        tk.Button(parent, text="📁  Datei wählen…",
                  command=self._add_file,
                  bg=ACCENT, fg="white", relief=tk.FLAT,
                  padx=8, pady=6, cursor="hand2",
                  font=("Helvetica", 11)).pack(**pad)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        tk.Label(parent, text="Track entfernen",
                 bg=SIDEBAR_BG, fg="#222",
                 font=("Helvetica", 12, "bold")).pack(anchor=tk.W, **pad)

        tk.Button(parent, text="🗑  Auswahl löschen",
                  command=self._remove_selected,
                  bg="#e74c3c", fg="white", relief=tk.FLAT,
                  padx=8, pady=6, cursor="hand2",
                  font=("Helvetica", 11)).pack(**pad)

        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        tk.Label(parent, text="YouTube Import",
                 bg=SIDEBAR_BG, fg="#222",
                 font=("Helvetica", 12, "bold")).pack(anchor=tk.W, **pad)

        tk.Label(parent, text="YouTube URL:",
                 bg=SIDEBAR_BG, fg="#444",
                 font=("Helvetica", 10)).pack(anchor=tk.W, padx=10)

        self._yt_url = tk.Entry(parent, font=("Helvetica", 10))
        self._yt_url.pack(**pad)
        self._yt_url.insert(0, "https://youtube.com/watch?v=…")
        self._yt_url.bind("<FocusIn>", self._clear_placeholder)

        tk.Button(parent, text="▶  Herunterladen & laden",
                  command=self._download_yt,
                  bg="#27ae60", fg="white", relief=tk.FLAT,
                  padx=8, pady=6, cursor="hand2",
                  font=("Helvetica", 11)).pack(**pad)

        # Tool-check label
        self._lbl_tools = tk.Label(parent, text="", bg=SIDEBAR_BG,
                                   fg="#888", font=("Helvetica", 9),
                                   wraplength=200, justify=tk.LEFT)
        self._lbl_tools.pack(anchor=tk.W, padx=10, pady=(4, 0))
        self._check_tools()

    # ----------------------------------------------------------------- tool check
    def _check_tools(self):
        msgs = []
        if not downloader.check_tool("yt-dlp"):
            msgs.append("⚠ yt-dlp nicht gefunden")
        if not downloader.check_tool("ffmpeg"):
            msgs.append("⚠ ffmpeg nicht gefunden")
        self._lbl_tools.config(
            text="\n".join(msgs) if msgs else "✓ yt-dlp & ffmpeg bereit")

    # ----------------------------------------------------------------- connect
    def _auto_connect(self):
        path = find_ipod()
        if path:
            self._connect(path)
        else:
            self._lbl_status.config(text="Kein iPod verbunden — USB anschließen")

    def _connect(self, path):
        try:
            db = iPodDB(path)
            self.tracks = db.load()
            self.db = db
            self.ipod_path = path
            name = ipod_name(path)
            free = db.free_space_gb()
            self._lbl_status.config(
                text=f"🎵  {name}  —  {len(self.tracks)} Tracks  |  {free:.1f} GB frei")
            self._populate_table()
        except Exception as e:
            messagebox.showerror("Verbindungsfehler",
                                 f"iPod konnte nicht gelesen werden:\n{e}")

    def _reload(self):
        if self.ipod_path and os.path.exists(
                os.path.join(self.ipod_path, "iPod_Control")):
            self._connect(self.ipod_path)
        else:
            self.ipod_path = None
            self.db = None
            self._lbl_status.config(text="Kein iPod verbunden")
            self._populate_table()
            self._auto_connect()

    # ----------------------------------------------------------------- table
    def _populate_table(self):
        self._tree.delete(*self._tree.get_children())
        for i, t in enumerate(self.tracks):
            vals = (
                t["title"] or "(kein Titel)",
                t["artist"] or "—",
                t["album"] or "—",
                fmt_duration(t["duration_ms"]),
                fmt_size(t["file_size"]),
            )
            tag = "odd" if i % 2 else "even"
            self._tree.insert("", tk.END, iid=str(t["id"]), values=vals, tags=(tag,))
        self._lbl_count.config(text=f"Tracks ({len(self.tracks)})")

    def _sort_by(self, col):
        key_map = {"Titel": "title", "Künstler": "artist",
                   "Album": "album", "Dauer": "duration_ms", "Größe": "file_size"}
        key = key_map.get(col, "title")
        self.tracks.sort(key=lambda t: (t[key] or "").lower()
                         if isinstance(t[key], str) else t[key])
        self._populate_table()

    # ----------------------------------------------------------------- actions
    def _add_file(self):
        if not self._check_connected():
            return
        paths = filedialog.askopenfilenames(
            title="Audiodatei wählen",
            filetypes=[("Audiodateien", "*.m4a *.mp3 *.aac *.mp4"),
                       ("Alle Dateien", "*.*")])
        if not paths:
            return
        for p in paths:
            self._run_in_thread(self._do_add, p)

    def _do_add(self, path):
        try:
            track = self.db.add_track(path, progress_cb=self._progress)
            self.tracks = self.db.load()
            self.after(0, self._populate_table)
            self.after(0, lambda: self._lbl_status.config(
                text=f"✓ '{track['title'][:40]}' hinzugefügt  —  {len(self.tracks)} Tracks"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            self.after(0, lambda: self._pb.config(value=0))

    def _remove_selected(self):
        if not self._check_connected():
            return
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte erst einen Track auswählen.")
            return
        track_id = int(sel[0])
        title = self._tree.item(sel[0], "values")[0]
        if not messagebox.askyesno("Track löschen",
                                   f"'{title}' wirklich vom iPod löschen?"):
            return
        self._run_in_thread(self._do_remove, track_id)

    def _do_remove(self, track_id):
        try:
            self.db.remove_track(track_id, progress_cb=self._progress)
            self.tracks = self.db.load()
            self.after(0, self._populate_table)
            self.after(0, lambda: self._lbl_status.config(
                text=f"Track gelöscht — {len(self.tracks)} Tracks verbleiben"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            self.after(0, lambda: self._pb.config(value=0))

    def _download_yt(self):
        if not self._check_connected():
            return
        url = self._yt_url.get().strip()
        if not url or url.startswith("https://youtube.com/watch?v=…"):
            messagebox.showwarning("URL fehlt", "Bitte eine YouTube-URL eingeben.")
            return
        if self._dl_thread and self._dl_thread.is_alive():
            messagebox.showinfo("Läuft bereits",
                                "Ein Download läuft bereits — bitte warten.")
            return
        self._run_in_thread(self._do_download, url)

    def _do_download(self, url):
        tmpdir = tempfile.mkdtemp(prefix="ipod_dl_")
        try:
            self._progress("Hole Video-Info…", 3)
            audio_path = downloader.download_audio(
                url, tmpdir, progress_cb=self._progress)
            self._progress("Füge zur Bibliothek hinzu…", 88)
            track = self.db.add_track(audio_path, progress_cb=None)
            self.tracks = self.db.load()
            self.after(0, self._populate_table)
            self.after(0, lambda: self._lbl_status.config(
                text=f"✓ '{track['title'][:40]}' hinzugefügt"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror(
                "Download-Fehler", str(e)))
        finally:
            # Clean up temp dir
            import shutil
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
            self.after(0, lambda: self._pb.config(value=0))
            self.after(0, lambda: self._lbl_progress.config(text=""))

    # ----------------------------------------------------------------- helpers
    def _check_connected(self):
        if not self.db:
            messagebox.showwarning("Kein iPod",
                                   "Bitte zuerst den iPod anschließen.")
            return False
        return True

    def _progress(self, msg, pct):
        self.after(0, lambda: self._pb.config(value=pct))
        self.after(0, lambda: self._lbl_progress.config(text=msg))

    def _run_in_thread(self, fn, *args):
        t = threading.Thread(target=fn, args=args, daemon=True)
        t.start()
        self._dl_thread = t

    def _clear_placeholder(self, event):
        if self._yt_url.get().startswith("https://youtube.com/watch?v=…"):
            self._yt_url.delete(0, tk.END)

    def _eject(self):
        if not self.ipod_path:
            return
        try:
            import subprocess, sys
            if sys.platform == "darwin":
                subprocess.run(["diskutil", "eject", self.ipod_path],
                               check=True, capture_output=True)
            elif sys.platform == "win32":
                messagebox.showinfo(
                    "iPod auswerfen",
                    "Bitte den iPod über 'Sicher entfernen' in der Taskleiste auswerfen.")
                return
            self.ipod_path = None
            self.db = None
            self.tracks = []
            self._populate_table()
            self._lbl_status.config(text="iPod ausgeworfen — kann sicher getrennt werden")
        except Exception as e:
            messagebox.showerror("Fehler beim Auswerfen", str(e))


if __name__ == "__main__":
    # Apply a clean ttk style
    app = App()
    style = ttk.Style(app)
    try:
        style.theme_use("aqua")   # macOS native
    except tk.TclError:
        try:
            style.theme_use("clam")  # Linux / Windows fallback
        except tk.TclError:
            pass

    style.configure("Treeview", rowheight=24, font=("Helvetica", 11))
    style.configure("Treeview.Heading", font=("Helvetica", 11, "bold"))
    app.mainloop()
