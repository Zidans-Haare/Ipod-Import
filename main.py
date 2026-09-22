"""iPod Manager — professionelle GUI."""

import os
import sys
import threading
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.ttk as ttk

import customtkinter as ctk

from ipod_db import find_ipod, ipod_name, iPodDB
import downloader

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

APP_TITLE = "iPod Manager"


def fmt_duration(ms):
    s = ms // 1000
    return f"{s // 60}:{s % 60:02d}"


def fmt_size(b):
    if b >= 1_000_000:
        return f"{b / 1_000_000:.1f} MB"
    return f"{b // 1000} KB"


class Sidebar(ctk.CTkScrollableFrame):
    """Left panel with all action controls."""

    def __init__(self, master, app, **kw):
        super().__init__(master, width=220, corner_radius=0,
                         fg_color=("gray92", "gray14"), **kw)
        self._app = app
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _section(self, row, text):
        ctk.CTkLabel(self, text=text,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=("gray50", "gray55"),
                     anchor="w").grid(row=row, column=0,
                                      padx=14, pady=(16, 4), sticky="ew")

    def _build(self):
        a = self._app
        p = dict(padx=10, pady=3, sticky="ew")

        self._section(0, "  HINZUFÜGEN")
        ctk.CTkButton(self, text="  📁  Datei laden…",
                      anchor="w", height=36,
                      command=a._add_file).grid(row=1, column=0, **p)

        self._section(2, "  YOUTUBE")
        self._url = ctk.CTkEntry(self, placeholder_text="YouTube-URL einfügen…",
                                 height=34)
        self._url.grid(row=3, column=0, **p)

        self._dl_btn = ctk.CTkButton(
            self, text="  ▶  Herunterladen",
            anchor="w", height=36,
            fg_color=("#27ae60", "#219653"),
            hover_color=("#219653", "#1a7a40"),
            command=a._download_yt)
        self._dl_btn.grid(row=4, column=0, **p)

        self._tool_lbl = ctk.CTkLabel(
            self, text="", wraplength=190, justify="left",
            font=ctk.CTkFont(size=11), text_color=("gray55", "gray50"), anchor="w")
        self._tool_lbl.grid(row=5, column=0, padx=14, pady=(2, 0), sticky="ew")

        self._section(6, "  AUSWAHL")
        ctk.CTkButton(self, text="  🗑  Löschen",
                      anchor="w", height=36,
                      fg_color=("#c0392b", "#962d22"),
                      hover_color=("#962d22", "#7a2419"),
                      command=a._remove_selected).grid(row=7, column=0, **p)

        # Spacer
        ctk.CTkLabel(self, text="").grid(row=8, column=0)

    @property
    def yt_url(self):
        return self._url.get().strip()

    def clear_url(self):
        self._url.delete(0, tk.END)

    def set_tool_status(self, text, ok):
        color = ("#27ae60", "#2ecc71") if ok else ("#e74c3c", "#c0392b")
        self._tool_lbl.configure(text=text, text_color=color)

    def set_dl_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self._dl_btn.configure(state=state)


class TrackTable(ctk.CTkFrame):
    """The main track list with search and sortable columns."""

    COLS = [
        ("Titel",     "title",       1,  300),
        ("Künstler",  "artist",      0,  170),
        ("Album",     "album",       0,  170),
        ("Dauer",     "duration_ms", 0,   68),
        ("Größe",     "file_size",   0,   78),
    ]

    def __init__(self, master, on_select=None, **kw):
        super().__init__(master, corner_radius=10,
                         fg_color=("white", "gray17"), **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._tracks: list[dict] = []
        self._sort_col: str | None = None
        self._sort_asc = True
        self._on_select = on_select
        self._query = ""

        self._build()

    def _build(self):
        # Search bar
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        bar.grid_columnconfigure(0, weight=1)

        self._count_lbl = ctk.CTkLabel(bar, text="",
                                        font=ctk.CTkFont(size=13, weight="bold"),
                                        anchor="w")
        self._count_lbl.grid(row=0, column=0, sticky="w")

        var = tk.StringVar()
        var.trace_add("write", lambda *_: self._on_search(var.get()))
        ctk.CTkEntry(bar, textvariable=var,
                     placeholder_text="🔍  Suchen…",
                     width=200, height=30).grid(row=0, column=1, sticky="e")

        # Treeview style
        mode = ctk.get_appearance_mode()
        bg   = "#2b2b2b" if mode == "Dark" else "#ffffff"
        fg   = "#e0e0e0" if mode == "Dark" else "#1a1a1a"
        hbg  = "#242424" if mode == "Dark" else "#f5f5f5"
        sel  = "#1f6aa5"
        abg  = "#323232" if mode == "Dark" else "#f9f9f9"

        s = ttk.Style()
        s.theme_use("default")
        s.configure("T.Treeview",
                    background=bg, foreground=fg, fieldbackground=bg,
                    rowheight=30, font=("Helvetica", 12), borderwidth=0)
        s.configure("T.Treeview.Heading",
                    background=hbg, foreground=fg,
                    font=("Helvetica", 11, "bold"), relief="flat", borderwidth=0)
        s.map("T.Treeview",
              background=[("selected", sel)],
              foreground=[("selected", "#ffffff")])
        s.layout("T.Treeview", [("T.Treeview.treearea", {"sticky": "nswe"})])

        cols = [c[0] for c in self.COLS]
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                   selectmode="browse", style="T.Treeview")
        self._tree.tag_configure("alt", background=abg)

        for label, key, stretch, w in self.COLS:
            self._tree.heading(label, text=label,
                               command=lambda k=key, l=label: self._sort(k, l))
            self._tree.column(label, width=w, minwidth=50,
                               stretch=bool(stretch))

        vsb = ctk.CTkScrollbar(self, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        self._tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))

    def load(self, tracks: list[dict]):
        self._tracks = list(tracks)
        self._sort_col = None
        self._refresh()

    def _refresh(self):
        q = self._query.lower()
        visible = [t for t in self._tracks if not q or any(
            q in (t.get(k) or "").lower() for k in ("title", "artist", "album"))]

        self._tree.delete(*self._tree.get_children())
        for i, t in enumerate(visible):
            vals = (
                t["title"]  or "(kein Titel)",
                t["artist"] or "—",
                t["album"]  or "—",
                fmt_duration(t["duration_ms"]),
                fmt_size(t["file_size"]),
            )
            tag = ("alt",) if i % 2 else ()
            self._tree.insert("", tk.END, iid=str(t["id"]), values=vals, tags=tag)

        total = len(self._tracks)
        shown = len(visible)
        self._count_lbl.configure(
            text=f"{shown} Songs" if shown == total else f"{shown} von {total} Songs")

    def _on_search(self, q: str):
        self._query = q
        self._refresh()

    def _sort(self, key: str, label: str):
        if self._sort_col == key:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_asc = True
            self._sort_col = key
        arrow = " ↑" if self._sort_asc else " ↓"
        for lbl, k, *_ in self.COLS:
            self._tree.heading(lbl, text=lbl + (arrow if k == key else ""))
        self._tracks.sort(
            key=lambda t: (t.get(key) or "").lower() if isinstance(t.get(key), str) else (t.get(key) or 0),
            reverse=not self._sort_asc)
        self._refresh()

    @property
    def selected_id(self) -> int | None:
        sel = self._tree.selection()
        return int(sel[0]) if sel else None

    @property
    def selected_title(self) -> str:
        sel = self._tree.selection()
        return self._tree.item(sel[0], "values")[0] if sel else ""


class StatusBar(ctk.CTkFrame):
    """Bottom bar with progress and status text."""

    def __init__(self, master, **kw):
        super().__init__(master, height=42, corner_radius=0,
                         fg_color=("gray90", "gray13"), **kw)
        self.grid_propagate(False)
        self.grid_columnconfigure(1, weight=1)

        self._pb = ctk.CTkProgressBar(self, width=180, height=10)
        self._pb.set(0)
        self._pb.grid(row=0, column=0, padx=(14, 10), pady=14)

        self._lbl = ctk.CTkLabel(self, text="Bereit",
                                  font=ctk.CTkFont(size=12),
                                  text_color=("gray40", "gray60"),
                                  anchor="w")
        self._lbl.grid(row=0, column=1, sticky="w")

    def update(self, msg: str, pct: float):
        self._pb.set(pct if pct <= 1 else pct / 100)
        self._lbl.configure(text=msg)

    def reset(self):
        self._pb.set(0)
        self._lbl.configure(text="Bereit")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1000x660")
        self.minsize(800, 520)

        self.ipod_path: str | None = None
        self.db: iPodDB | None = None
        self.tracks: list[dict] = []
        self._dl_thread: threading.Thread | None = None

        self._build()
        self._after_init()

    # ------------------------------------------------------------ build
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Top bar
        top = ctk.CTkFrame(self, height=52, corner_radius=0,
                            fg_color=("gray88", "gray15"))
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        top.grid_propagate(False)

        self._dev_icon = ctk.CTkLabel(top, text="🎵",
                                       font=ctk.CTkFont(size=20))
        self._dev_icon.grid(row=0, column=0, padx=(16, 6), pady=10)

        self._status_lbl = ctk.CTkLabel(
            top, text="Kein iPod verbunden",
            font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
        self._status_lbl.grid(row=0, column=1, sticky="w", pady=10)

        btn_f = ctk.CTkFrame(top, fg_color="transparent")
        btn_f.grid(row=0, column=2, padx=12, pady=8)

        ctk.CTkButton(btn_f, text="⏏  Auswerfen", width=120, height=32,
                      fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray25"),
                      font=ctk.CTkFont(size=12),
                      command=self._eject).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_f, text="⟳  Aktualisieren", width=130, height=32,
                      font=ctk.CTkFont(size=12),
                      command=self._reload).pack(side="left")

        # Sidebar
        self._sidebar = Sidebar(self, app=self)
        self._sidebar.grid(row=1, column=0, sticky="nsew")

        # Track table
        self._table = TrackTable(self)
        self._table.grid(row=1, column=1, sticky="nsew", padx=12, pady=12)

        # Status bar
        self._statusbar = StatusBar(self)
        self._statusbar.grid(row=2, column=0, columnspan=2, sticky="ew")

    def _after_init(self):
        self._check_tools()
        self._auto_connect()

    # ---------------------------------------------------------- tools
    def _check_tools(self):
        yt  = downloader.check_tool("yt-dlp")
        ff  = downloader.check_tool("ffmpeg")
        if yt:
            self._sidebar.set_tool_status("✓ YouTube-Download bereit", True)
        else:
            self._sidebar.set_tool_status("⚠ yt-dlp nicht gefunden", False)

    # --------------------------------------------------------- connect
    def _auto_connect(self):
        path = find_ipod()
        if path:
            self._connect(path)
        else:
            self._status_lbl.configure(text="Kein iPod verbunden — USB anschließen")
            self._dev_icon.configure(text="🔌")

    def _connect(self, path: str):
        try:
            db = iPodDB(path)
            self.tracks = db.load()
            self.db = db
            self.ipod_path = path
            name = ipod_name(path)
            free = db.free_space_gb()
            self._status_lbl.configure(
                text=f"{name}  ·  {len(self.tracks)} Songs  ·  {free:.1f} GB frei")
            self._dev_icon.configure(text="🎵")
            self._table.load(self.tracks)
            self._statusbar.reset()
        except Exception as e:
            messagebox.showerror("Fehler", f"iPod konnte nicht gelesen werden:\n{e}")

    def _reload(self):
        if self.ipod_path and os.path.exists(
                os.path.join(self.ipod_path, "iPod_Control")):
            self._connect(self.ipod_path)
        else:
            self.ipod_path = None
            self.db = None
            self.tracks = []
            self._table.load([])
            self._auto_connect()

    # --------------------------------------------------------- actions
    def _add_file(self):
        if not self._need_ipod():
            return
        paths = filedialog.askopenfilenames(
            title="Audiodatei wählen",
            filetypes=[("Audio", "*.m4a *.mp3 *.aac *.mp4"), ("Alle", "*.*")])
        if paths:
            self._run(self._do_add, list(paths))

    def _do_add(self, paths: list[str]):
        for p in paths:
            name = os.path.basename(p)
            try:
                self._progress(f"Kopiere {name}…", 0.2)
                track = self.db.add_track(p, progress_cb=self._progress)
                self.tracks = self.db.load()
                self.after(0, lambda: self._table.load(self.tracks))
                self.after(0, lambda t=track: self._set_status(
                    f"✓  »{t['title'][:45]}« hinzugefügt  ·  {len(self.tracks)} Songs"))
            except Exception as e:
                self.after(0, lambda err=str(e): messagebox.showerror("Fehler", err))
        self.after(0, lambda: self._statusbar.reset())

    def _remove_selected(self):
        if not self._need_ipod():
            return
        tid = self._table.selected_id
        if tid is None:
            messagebox.showinfo("Hinweis", "Bitte zuerst einen Song auswählen.")
            return
        title = self._table.selected_title
        if messagebox.askyesno("Song löschen", f"»{title}« wirklich vom iPod löschen?"):
            self._run(self._do_remove, tid)

    def _do_remove(self, tid: int):
        try:
            self.db.remove_track(tid, progress_cb=self._progress)
            self.tracks = self.db.load()
            self.after(0, lambda: self._table.load(self.tracks))
            self.after(0, lambda: self._set_status(
                f"Song gelöscht  ·  {len(self.tracks)} Songs verbleiben"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Fehler", str(e)))
        finally:
            self.after(0, self._statusbar.reset)

    def _download_yt(self):
        if not self._need_ipod():
            return
        url = self._sidebar.yt_url
        if not url or ("youtube" not in url and "youtu.be" not in url):
            messagebox.showwarning("URL fehlt",
                                   "Bitte eine gültige YouTube-URL eingeben.")
            return
        if self._dl_thread and self._dl_thread.is_alive():
            messagebox.showinfo("Läuft noch", "Ein Download läuft bereits — bitte warten.")
            return
        self._sidebar.set_dl_busy(True)
        self._run(self._do_download, url)

    def _do_download(self, url: str):
        tmpdir = tempfile.mkdtemp(prefix="ipod_dl_")
        try:
            audio, meta = downloader.download_audio(url, tmpdir,
                                                    progress_cb=self._progress)
            self._progress("Füge zum iPod hinzu…", 0.9)
            track = self.db.add_track(audio,
                                      title=meta.get("title") or None,
                                      artist=meta.get("artist") or None,
                                      album=meta.get("album") or None,
                                      progress_cb=None)
            self.tracks = self.db.load()
            self.after(0, lambda: self._table.load(self.tracks))
            self.after(0, lambda t=track: self._set_status(
                f"✓  »{t['title'][:45]}« heruntergeladen & hinzugefügt  ·  {len(self.tracks)} Songs"))
            self.after(0, self._sidebar.clear_url)
        except Exception as e:
            self.after(0, lambda err=str(e): messagebox.showerror("Download-Fehler", err))
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
            self.after(0, self._statusbar.reset)
            self.after(0, lambda: self._sidebar.set_dl_busy(False))

    # --------------------------------------------------------- helpers
    def _need_ipod(self) -> bool:
        if not self.db:
            messagebox.showwarning("Kein iPod", "Bitte zuerst den iPod anschließen.")
            return False
        return True

    def _progress(self, msg: str, pct: float):
        self.after(0, lambda: self._statusbar.update(msg, pct))

    def _set_status(self, text: str):
        self._status_lbl.configure(text=text)

    def _run(self, fn, *args):
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
            self.ipod_path = None
            self.db = None
            self.tracks = []
            self._table.load([])
            self._status_lbl.configure(text="iPod ausgeworfen ✓")
            self._dev_icon.configure(text="🔌")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))


if __name__ == "__main__":
    app = App()
    app.mainloop()
