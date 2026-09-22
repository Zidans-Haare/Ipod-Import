"""iPod Manager — moderne GUI mit customtkinter."""

import os
import sys
import threading
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ipod_db import find_ipod, ipod_name, iPodDB
import downloader

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

APP_TITLE  = "iPod Manager"
APP_WIDTH  = 960
APP_HEIGHT = 640


def fmt_duration(ms):
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def fmt_size(b):
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} MB"
    return f"{b // 1000} KB"


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.minsize(800, 500)

        self.ipod_path = None
        self.db: iPodDB | None = None
        self.tracks = []
        self._dl_thread = None
        self._sort_col = None
        self._sort_asc = True

        self._build_ui()
        self._auto_connect()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Top bar ──────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, height=56, corner_radius=0)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        top.grid_propagate(False)

        self._lbl_status = ctk.CTkLabel(
            top, text="Kein iPod verbunden",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w")
        self._lbl_status.grid(row=0, column=0, padx=18, pady=14, sticky="w")

        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=12, pady=8, sticky="e")

        ctk.CTkButton(btn_frame, text="⟳  Aktualisieren", width=140,
                      command=self._reload).pack(side="right", padx=(6, 0))
        ctk.CTkButton(btn_frame, text="⏏  Auswerfen", width=130,
                      fg_color="gray40", hover_color="gray30",
                      command=self._eject).pack(side="right")

        # ── Sidebar (links) ───────────────────────────────────────────────
        sidebar = ctk.CTkFrame(self, width=230, corner_radius=0)
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_rowconfigure(10, weight=1)
        sidebar.grid_propagate(False)

        pad = dict(padx=14, pady=4, sticky="ew")

        # Datei hinzufügen
        ctk.CTkLabel(sidebar, text="MUSIK HINZUFÜGEN",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray60").grid(row=0, column=0, padx=14, pady=(18, 4), sticky="w")

        ctk.CTkButton(sidebar, text="📁  Datei wählen…",
                      command=self._add_file).grid(row=1, column=0, **pad)

        ctk.CTkLabel(sidebar, text="YOUTUBE IMPORT",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray60").grid(row=2, column=0, padx=14, pady=(18, 4), sticky="w")

        ctk.CTkLabel(sidebar, text="YouTube URL:",
                     font=ctk.CTkFont(size=12),
                     anchor="w").grid(row=3, column=0, padx=14, sticky="w")

        self._yt_url = ctk.CTkEntry(sidebar, placeholder_text="https://youtube.com/watch?v=…")
        self._yt_url.grid(row=4, column=0, **pad)

        ctk.CTkButton(sidebar, text="▶  Herunterladen & laden",
                      fg_color="#27ae60", hover_color="#219653",
                      command=self._download_yt).grid(row=5, column=0, **pad)

        self._lbl_tools = ctk.CTkLabel(sidebar, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color="gray50",
                                       wraplength=200, justify="left", anchor="w")
        self._lbl_tools.grid(row=6, column=0, padx=14, pady=(2, 0), sticky="w")
        self._check_tools()

        ctk.CTkLabel(sidebar, text="AUSWAHL",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="gray60").grid(row=7, column=0, padx=14, pady=(18, 4), sticky="w")

        ctk.CTkButton(sidebar, text="🗑  Track löschen",
                      fg_color="#c0392b", hover_color="#962d22",
                      command=self._remove_selected).grid(row=8, column=0, **pad)

        # ── Haupt-Bereich (rechts) ────────────────────────────────────────
        main = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        main.grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # Suchleiste + Track-Zähler
        search_row = ctk.CTkFrame(main, fg_color="transparent")
        search_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 6))
        search_row.grid_columnconfigure(1, weight=1)

        self._lbl_count = ctk.CTkLabel(search_row, text="Tracks (0)",
                                       font=ctk.CTkFont(size=13, weight="bold"),
                                       anchor="w")
        self._lbl_count.grid(row=0, column=0, padx=(0, 12), sticky="w")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_table())
        self._search_entry = ctk.CTkEntry(search_row, textvariable=self._search_var,
                                          placeholder_text="🔍  Suchen…", width=220)
        self._search_entry.grid(row=0, column=1, sticky="e")

        # Track-Tabelle via ttk.Treeview (customtkinter hat noch keine)
        import tkinter.ttk as ttk
        style = ttk.Style()
        style.theme_use("default")
        bg = self._get_bg_color()
        fg = "#ffffff" if ctk.get_appearance_mode() == "Dark" else "#111111"
        sel_bg = "#1f6aa5"
        style.configure("iPod.Treeview",
                         background=bg, foreground=fg,
                         fieldbackground=bg,
                         rowheight=28, font=("Helvetica", 12),
                         borderwidth=0, relief="flat")
        style.configure("iPod.Treeview.Heading",
                         font=("Helvetica", 12, "bold"),
                         background=bg, foreground=fg,
                         relief="flat", borderwidth=0)
        style.map("iPod.Treeview",
                  background=[("selected", sel_bg)],
                  foreground=[("selected", "#ffffff")])
        style.layout("iPod.Treeview", [("iPod.Treeview.treearea", {"sticky": "nswe"})])

        tree_frame = ctk.CTkFrame(main, corner_radius=8)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 0))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        cols = ("Titel", "Künstler", "Album", "Dauer", "Größe")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   selectmode="browse", style="iPod.Treeview")
        widths = (300, 180, 180, 70, 80)
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=w, minwidth=40)

        vsb = ctk.CTkScrollbar(tree_frame, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.grid(row=0, column=0, sticky="nsew")

        # ── Statusleiste (unten) ──────────────────────────────────────────
        bot = ctk.CTkFrame(self, height=38, corner_radius=0)
        bot.grid(row=2, column=0, columnspan=2, sticky="ew")
        bot.grid_columnconfigure(1, weight=1)
        bot.grid_propagate(False)

        self._pb = ctk.CTkProgressBar(bot, width=200, height=12)
        self._pb.set(0)
        self._pb.grid(row=0, column=0, padx=14, pady=12)

        self._lbl_progress = ctk.CTkLabel(bot, text="",
                                          font=ctk.CTkFont(size=11),
                                          anchor="w")
        self._lbl_progress.grid(row=0, column=1, padx=6, sticky="w")

    def _get_bg_color(self):
        mode = ctk.get_appearance_mode()
        return "#2b2b2b" if mode == "Dark" else "#f0f0f0"

    # ---------------------------------------------------------------- tools
    def _check_tools(self):
        msgs = []
        if not downloader.check_tool("yt-dlp"):
            msgs.append("⚠ yt-dlp fehlt")
        if not downloader.check_tool("ffmpeg"):
            msgs.append("⚠ ffmpeg fehlt")
        self._lbl_tools.configure(
            text="\n".join(msgs) if msgs else "✓ yt-dlp & ffmpeg bereit")

    # --------------------------------------------------------------- connect
    def _auto_connect(self):
        path = find_ipod()
        if path:
            self._connect(path)
        else:
            self._lbl_status.configure(text="Kein iPod verbunden — USB anschließen")

    def _connect(self, path):
        try:
            db = iPodDB(path)
            self.tracks = db.load()
            self.db = db
            self.ipod_path = path
            name = ipod_name(path)
            free = db.free_space_gb()
            self._lbl_status.configure(
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
            self._lbl_status.configure(text="Kein iPod verbunden")
            self._populate_table()
            self._auto_connect()

    # --------------------------------------------------------------- table
    def _populate_table(self, tracks=None):
        self._tree.delete(*self._tree.get_children())
        source = tracks if tracks is not None else self.tracks
        for t in source:
            vals = (
                t["title"] or "(kein Titel)",
                t["artist"] or "—",
                t["album"] or "—",
                fmt_duration(t["duration_ms"]),
                fmt_size(t["file_size"]),
            )
            self._tree.insert("", tk.END, iid=str(t["id"]), values=vals)
        total = len(self.tracks)
        shown = len(source)
        if shown < total:
            self._lbl_count.configure(text=f"Tracks ({shown} von {total})")
        else:
            self._lbl_count.configure(text=f"Tracks ({total})")

    def _filter_table(self):
        q = self._search_var.get().lower().strip()
        if not q:
            self._populate_table()
            return
        filtered = [t for t in self.tracks if
                    q in (t["title"] or "").lower() or
                    q in (t["artist"] or "").lower() or
                    q in (t["album"] or "").lower()]
        self._populate_table(filtered)

    def _sort_by(self, col):
        key_map = {"Titel": "title", "Künstler": "artist",
                   "Album": "album", "Dauer": "duration_ms", "Größe": "file_size"}
        key = key_map.get(col, "title")
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_asc = True
            self._sort_col = col
        self.tracks.sort(
            key=lambda t: (t[key] or "").lower() if isinstance(t[key], str) else t[key],
            reverse=not self._sort_asc)
        self._filter_table()

    # --------------------------------------------------------------- actions
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
            self.after(0, self._filter_table)
            self.after(0, lambda: self._lbl_status.configure(
                text=f"✓ '{track['title'][:40]}' hinzugefügt  —  {len(self.tracks)} Tracks"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            self.after(0, lambda: self._pb.set(0))

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
            self.after(0, self._filter_table)
            self.after(0, lambda: self._lbl_status.configure(
                text=f"Track gelöscht — {len(self.tracks)} Tracks verbleiben"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            self.after(0, lambda: self._pb.set(0))

    def _download_yt(self):
        if not self._check_connected():
            return
        url = self._yt_url.get().strip()
        if not url or "youtube" not in url.lower() and "youtu.be" not in url.lower():
            messagebox.showwarning("URL fehlt", "Bitte eine gültige YouTube-URL eingeben.")
            return
        if self._dl_thread and self._dl_thread.is_alive():
            messagebox.showinfo("Läuft bereits", "Ein Download läuft bereits — bitte warten.")
            return
        self._run_in_thread(self._do_download, url)

    def _do_download(self, url):
        tmpdir = tempfile.mkdtemp(prefix="ipod_dl_")
        try:
            self._progress("Hole Video-Info…", 0.03)
            audio_path = downloader.download_audio(url, tmpdir, progress_cb=self._progress)
            self._progress("Füge zur Bibliothek hinzu…", 0.88)
            track = self.db.add_track(audio_path, progress_cb=None)
            self.tracks = self.db.load()
            self.after(0, self._filter_table)
            self.after(0, lambda: self._lbl_status.configure(
                text=f"✓ '{track['title'][:40]}' hinzugefügt"))
            self.after(0, lambda: self._yt_url.delete(0, tk.END))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Download-Fehler", str(e)))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.after(0, lambda: self._pb.set(0))
            self.after(0, lambda: self._lbl_progress.configure(text=""))

    # --------------------------------------------------------------- helpers
    def _check_connected(self):
        if not self.db:
            messagebox.showwarning("Kein iPod", "Bitte zuerst den iPod anschließen.")
            return False
        return True

    def _progress(self, msg, pct):
        self.after(0, lambda: self._pb.set(pct / 100 if pct > 1 else pct))
        self.after(0, lambda: self._lbl_progress.configure(text=msg))

    def _run_in_thread(self, fn, *args):
        t = threading.Thread(target=fn, args=args, daemon=True)
        t.start()
        self._dl_thread = t

    def _eject(self):
        if not self.ipod_path:
            return
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.run(["diskutil", "eject", self.ipod_path],
                               check=True, capture_output=True)
            elif sys.platform == "win32":
                messagebox.showinfo("iPod auswerfen",
                    "Bitte den iPod über 'Sicher entfernen' in der Taskleiste auswerfen.")
                return
            self.ipod_path = None
            self.db = None
            self.tracks = []
            self._populate_table()
            self._lbl_status.configure(text="iPod ausgeworfen ✓")
        except Exception as e:
            messagebox.showerror("Fehler beim Auswerfen", str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()
