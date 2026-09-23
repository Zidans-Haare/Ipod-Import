"""iPod classic iTunesDB management."""

import os, sys, struct, shutil, string, random, time, glob, hashlib, subprocess
from pathlib import Path

UNIX_TO_MAC = 2082844800  # seconds between 1904-01-01 and 1970-01-01

# ---------------------------------------------------------------------------
# hash58 — required on iPod classic 6G/7G and nano 3G/4G.
# Algorithm reverse-engineered by wtbw, first implemented in libgpod
# by Christophe Fergeau. Independent Python re-implementation.
# ---------------------------------------------------------------------------

_AES_SBOX = [
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16,
]
_AES_ISBOX = [0] * 256
for _i, _v in enumerate(_AES_SBOX):
    _AES_ISBOX[_v] = _i

_H58_FIXED = bytes([
    0x67,0x23,0xFE,0x30,0x45,0x33,0xF8,0x90,0x99,
    0x21,0x07,0xC1,0xD0,0x12,0xB2,0xA1,0x07,0x81,
])


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def _hash58_key(guid_bytes: bytes) -> bytes:
    y = []
    for i in range(4):
        a, b = guid_bytes[i * 2], guid_bytes[i * 2 + 1]
        l = (a * b) // _gcd(a, b) if (a and b) else 1
        hi, lo = (l >> 8) & 0xFF, l & 0xFF
        y += [_AES_SBOX[hi], _AES_ISBOX[hi], _AES_SBOX[lo], _AES_ISBOX[lo]]
    seed = _H58_FIXED + bytes(y)
    return hashlib.sha1(seed).digest() + b"\x00" * 44   # 64-byte HMAC key


def _hash58_sign(db: bytearray, guid_bytes: bytes) -> None:
    """Compute hash58 and write it in-place at offset 0x58."""
    saved = [bytes(db[s:s + n]) for s, n in ((0x18, 8), (0x32, 20), (0x58, 20))]
    for s, n in ((0x18, 8), (0x32, 20), (0x58, 20)):
        db[s:s + n] = b"\x00" * n
    key64 = _hash58_key(guid_bytes)
    inner = bytes(k ^ 0x36 for k in key64) + bytes(db)
    outer_key = bytes(k ^ 0x5C for k in key64)
    mac = hashlib.sha1(outer_key + hashlib.sha1(inner).digest()).digest()
    for (s, _), orig in zip(((0x18, 8), (0x32, 20), (0x58, 20)), saved):
        db[s:s + len(orig)] = orig
    db[0x58:0x6c] = mac


def _get_firewire_guid(ipod_path: str) -> bytes | None:
    """Try to read the FireWire GUID for the connected iPod."""
    # 1. From SysInfoExtended (standard libgpod location)
    sie = os.path.join(ipod_path, "iPod_Control", "Device", "SysInfoExtended")
    if os.path.exists(sie):
        try:
            with open(sie) as f:
                for line in f:
                    if "FireWireGUID" in line:
                        hex_str = line.split(":")[-1].strip().replace("0x", "")
                        if len(hex_str) == 16:
                            return bytes.fromhex(hex_str)
        except Exception:
            pass
    # 2. From USB serial number via ioreg (macOS only)
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["ioreg", "-r", "-n", "iPod"],
                stderr=subprocess.DEVNULL, timeout=5
            ).decode(errors="ignore")
            for line in out.splitlines():
                if "kUSBSerialNumberString" in line or "USB Serial Number" in line:
                    parts = line.split('"')
                    for p in parts:
                        p = p.strip()
                        if len(p) == 16 and all(c in "0123456789ABCDEFabcdef" for c in p):
                            return bytes.fromhex(p)
        except Exception:
            pass
    return None


def find_ipod():
    """Return the mount path of a connected iPod, or None."""
    if sys.platform == "darwin":
        for p in glob.glob("/Volumes/*/iPod_Control/iTunes/iTunesDB"):
            return str(Path(p).parents[2])
    elif sys.platform == "win32":
        for drive in string.ascii_uppercase:
            if os.path.exists(f"{drive}:\\iPod_Control\\iTunes\\iTunesDB"):
                return f"{drive}:\\"
    return None


def ipod_name(ipod_path):
    return os.path.basename(ipod_path)


class iPodDB:
    def __init__(self, ipod_path):
        self.path = ipod_path
        self.db = os.path.join(ipod_path, "iPod_Control", "iTunes", "iTunesDB")
        self.music_dir = os.path.join(ipod_path, "iPod_Control", "Music")
        self._data = None
        self._tracks_raw = []   # list of (offset, hdr_size, total_size, track_id)
        # Key offsets discovered during load
        self._mhbd_total_off = 8
        self._mhlt_off = None
        self._mhsd_track_off = None

    # ------------------------------------------------------------------ load
    def load(self):
        """Parse iTunesDB and return list of track dicts."""
        with open(self.db, "rb") as f:
            self._data = bytearray(f.read())
        d = self._data

        mhlt_pos = d.find(b"mhlt")
        if mhlt_pos == -1:
            raise ValueError("mhlt nicht gefunden")
        self._mhlt_off = mhlt_pos

        # The mhsd section that contains mhlt
        mhsd_pos = d.rfind(b"mhsd", 0, mhlt_pos)
        if mhsd_pos == -1:
            raise ValueError("mhsd nicht gefunden")
        self._mhsd_track_off = mhsd_pos

        return self._parse_tracks()

    def _parse_tracks(self):
        d = self._data
        mhlt_hdr = struct.unpack_from("<I", d, self._mhlt_off + 4)[0]
        mhsd_total = struct.unpack_from("<I", d, self._mhsd_track_off + 8)[0]
        section_end = self._mhsd_track_off + mhsd_total

        tracks = []
        self._tracks_raw = []
        off = self._mhlt_off + mhlt_hdr

        while off < section_end:
            if d[off:off + 4] != b"mhit":
                break
            mhit_hdr = struct.unpack_from("<I", d, off + 4)[0]
            mhit_total = struct.unpack_from("<I", d, off + 8)[0]
            tid = struct.unpack_from("<I", d, off + 16)[0]

            fields = {}
            mo = off + mhit_hdr
            while mo < off + mhit_total:
                if d[mo:mo + 4] != b"mhod":
                    break
                m_total = struct.unpack_from("<I", d, mo + 8)[0]
                m_type = struct.unpack_from("<I", d, mo + 12)[0]
                if m_type in (1, 2, 3, 4, 5, 6):
                    slen = struct.unpack_from("<I", d, mo + 28)[0]
                    try:
                        fields[m_type] = d[mo + 40:mo + 40 + slen].decode("utf-16-le").rstrip("\x00")
                    except Exception:
                        fields[m_type] = ""
                mo += m_total

            tracks.append({
                "id": tid,
                "title": fields.get(1, ""),
                "artist": fields.get(4, ""),
                "album": fields.get(3, ""),
                "genre": fields.get(5, ""),
                "filename": fields.get(2, ""),
                "duration_ms": struct.unpack_from("<I", d, off + 40)[0],
                "file_size": struct.unpack_from("<I", d, off + 36)[0],
                "bitrate": struct.unpack_from("<I", d, off + 56)[0],
                "year": struct.unpack_from("<I", d, off + 52)[0],
                "_offset": off,
                "_total": mhit_total,
            })
            self._tracks_raw.append((off, mhit_hdr, mhit_total, tid))
            off += mhit_total

        return tracks

    # ------------------------------------------------------- DB-Record builders
    def _mhod(self, type_id, text):
        utf16 = text.encode("utf-16-le")
        total = 40 + len(utf16)
        return (struct.pack("<4sIIIIII", b"mhod", 24, total, type_id, 0, 0, 1)
                + struct.pack("<II", len(utf16), 1)
                + b"\x00" * 4
                + utf16)

    def _mhit(self, tid, fsize, dur_ms, brate, srate, year,
              dbid_lo, dbid_hi, ts, mhods, is_mp3=False):
        body = b"".join(mhods)
        total = 624 + len(body)
        h = bytearray(624)
        struct.pack_into("<4s", h, 0, b"mhit")
        struct.pack_into("<I", h, 4, 624)
        struct.pack_into("<I", h, 8, total)
        struct.pack_into("<I", h, 12, len(mhods))
        struct.pack_into("<I", h, 16, tid)
        struct.pack_into("<I", h, 20, 1)                   # visible
        struct.pack_into("<4s", h, 24, b"3PM " if is_mp3 else b" A4M")
        struct.pack_into("<H", h, 28, 1)
        struct.pack_into("<I", h, 32, ts)
        struct.pack_into("<I", h, 36, fsize)
        struct.pack_into("<I", h, 40, dur_ms)
        struct.pack_into("<I", h, 52, year)
        struct.pack_into("<I", h, 56, brate)
        struct.pack_into("<I", h, 60, srate << 16)
        struct.pack_into("<I", h, 92,  1)                  # disc_count flag
        struct.pack_into("<I", h, 100, ts)                 # date_added
        struct.pack_into("<I", h, 112, dbid_lo)
        struct.pack_into("<I", h, 116, dbid_hi)
        struct.pack_into("<I", h, 164, 1)                  # media_kind = music
        struct.pack_into("<I", h, 208, 1)                  # media flag
        struct.pack_into("<I", h, 256, 1)                  # media flag
        struct.pack_into("<I", h, 292, 4100818589)         # required constant
        struct.pack_into("<I", h, 296, 3804670695)         # required constant
        struct.pack_into("<I", h, 308, 2155905152)         # required constant
        struct.pack_into("<H", h, 312, 32896)              # required constant
        struct.pack_into("<I", h, 360, 1)                  # media flag
        struct.pack_into("<I", h, 524, 2)                  # required constant
        struct.pack_into("<I", h, 580, 16777216)           # required constant
        struct.pack_into("<I", h, 596, 3872851678)         # required constant
        return bytes(h) + body

    def _mhip(self, tid, dbid_lo, dbid_hi, ts, seq):
        h = bytearray(76)
        struct.pack_into("<4s", h, 0, b"mhip")
        struct.pack_into("<I", h, 4, 76)
        struct.pack_into("<I", h, 8, 120)   # 76 hdr + 44 mhod
        struct.pack_into("<I", h, 12, 1)
        struct.pack_into("<I", h, 20, seq)
        struct.pack_into("<I", h, 24, tid)
        struct.pack_into("<I", h, 28, ts)
        struct.pack_into("<I", h, 44, dbid_lo)
        struct.pack_into("<I", h, 48, dbid_hi)
        mhod = struct.pack("<4sIIIIIIIIII", b"mhod", 24, 44, 100, 0, 0, 0, 0, 0, 0, 0)
        return bytes(h) + mhod

    # ------------------------------------------ find playlist insert points
    def _playlist_sections(self, data):
        """Return list of dicts describing where to insert mhip records."""
        results = []
        pos = 0
        while pos < len(data) - 8:
            idx = data.find(b"mhsd", pos)
            if idx == -1:
                break
            mhsd_hdr   = struct.unpack_from("<I", data, idx + 4)[0]
            mhsd_total = struct.unpack_from("<I", data, idx + 8)[0]
            mhsd_type  = struct.unpack_from("<I", data, idx + 12)[0]
            if mhsd_type in (2, 3):
                mhlp_pos = idx + mhsd_hdr
                if data[mhlp_pos:mhlp_pos + 4] == b"mhlp":
                    mhlp_hdr = struct.unpack_from("<I", data, mhlp_pos + 4)[0]
                    mhyp_pos = mhlp_pos + mhlp_hdr
                    if data[mhyp_pos:mhyp_pos + 4] == b"mhyp":
                        mhyp_hdr  = struct.unpack_from("<I", data, mhyp_pos + 4)[0]
                        mhyp_total = struct.unpack_from("<I", data, mhyp_pos + 8)[0]
                        master     = struct.unpack_from("<I", data, mhyp_pos + 20)[0]
                        if master == 1:
                            mhyp_end = mhyp_pos + mhyp_total
                            last_seq = 0
                            c = mhyp_pos + mhyp_hdr
                            while c < mhyp_end:
                                tag = data[c:c + 4]
                                if tag == b"mhip":
                                    seq = struct.unpack_from("<I", data, c + 20)[0]
                                    if seq > last_seq:
                                        last_seq = seq
                                    c += struct.unpack_from("<I", data, c + 8)[0]
                                elif tag == b"mhod":
                                    c += struct.unpack_from("<I", data, c + 8)[0]
                                else:
                                    break
                            results.append(dict(
                                mhsd_total_off=idx + 8,
                                mhyp_total_off=mhyp_pos + 8,
                                mhyp_ch_off=mhyp_pos + 12,
                                mhyp_tr_off=mhyp_pos + 16,
                                insert_at=mhyp_end,
                                last_seq=last_seq,
                            ))
            pos = idx + mhsd_total
        return results

    # -------------------------------------------------------------- add track
    def add_track(self, audio_path, title=None, artist=None, album=None,
                  genre=None, progress_cb=None):
        """Add audio file to iPod. Returns track dict. Raises on error."""
        def _cb(msg, pct):
            if progress_cb:
                progress_cb(msg, pct)

        _cb("Lese Metadaten…", 5)

        ext = os.path.splitext(audio_path)[1].lower()
        dur_ms, brate, srate, year = 0, 128, 44100, 0

        try:
            from mutagen.mp4 import MP4
            from mutagen.mp3 import MP3
            if ext in (".m4a", ".aac", ".mp4"):
                a = MP4(audio_path)
                dur_ms = int(a.info.length * 1000)
                brate = max(1, (a.info.bitrate or 128000) // 1000)
                srate = a.info.sample_rate
                if a.tags:
                    title  = title  or str(a.tags.get("\xa9nam", [""])[0]) or None
                    artist = artist or str(a.tags.get("\xa9ART", [""])[0]) or None
                    album  = album  or str(a.tags.get("\xa9alb", [""])[0]) or None
                    genre  = genre  or str(a.tags.get("\xa9gen", [""])[0]) or None
                    try: year = int(str(a.tags.get("\xa9day", ["0"])[0])[:4])
                    except Exception: pass
            elif ext == ".mp3":
                a = MP3(audio_path)
                dur_ms = int(a.info.length * 1000)
                brate = max(1, int(a.info.bitrate or 128))
                srate = a.info.sample_rate
                try:
                    from mutagen.id3 import ID3
                    tags = ID3(audio_path)
                    title  = title  or (str(tags["TIT2"]) if "TIT2" in tags else None)
                    artist = artist or (str(tags["TPE1"]) if "TPE1" in tags else None)
                    album  = album  or (str(tags["TALB"]) if "TALB" in tags else None)
                    genre  = genre  or (str(tags["TCON"]) if "TCON" in tags else None)
                    if "TDRC" in tags:
                        try: year = int(str(tags["TDRC"])[:4])
                        except Exception: pass
                except Exception: pass
        except Exception as e:
            raise RuntimeError(f"Metadaten konnten nicht gelesen werden: {e}")

        title  = title  or os.path.splitext(os.path.basename(audio_path))[0]
        artist = artist or ""
        album  = album  or ""
        genre  = genre  or ""
        fsize  = os.path.getsize(audio_path)

        # Pick folder with fewest files
        folders = {f: len(os.listdir(os.path.join(self.music_dir, f)))
                   for f in os.listdir(self.music_dir)
                   if os.path.isdir(os.path.join(self.music_dir, f)) and f.startswith("F")}
        if not folders:
            raise RuntimeError("Keine F0x-Musikordner auf iPod gefunden")
        folder = min(folders, key=folders.get)
        existing = set(os.listdir(os.path.join(self.music_dir, folder)))
        random.seed()
        while True:
            fname = "".join(random.choices(string.ascii_uppercase, k=4)) + ext
            if fname not in existing:
                break

        ipod_path = f":iPod_Control:Music:{folder}:{fname}"
        dest = os.path.join(self.music_dir, folder, fname)

        max_id = max((t[3] for t in self._tracks_raw), default=0)
        new_id = max_id + 2
        dbid_lo = random.randint(0x10000000, 0xFFFFFFFF)
        dbid_hi = random.randint(0x10000000, 0xFFFFFFFF)
        ts = int(time.time()) + UNIX_TO_MAC

        _cb("Baue Datenbankeinträge…", 20)

        kind = "AAC-Audiodatei" if ext != ".mp3" else "MPEG-Audiodatei"
        mhods = [
            self._mhod(1, title),
            self._mhod(2, ipod_path),
            self._mhod(4, artist),
            self._mhod(3, album),
            self._mhod(5, genre),
            self._mhod(6, kind),
        ]
        new_mhit = self._mhit(new_id, fsize, dur_ms, brate, srate, year,
                               dbid_lo, dbid_hi, ts, mhods, is_mp3=(ext == ".mp3"))

        with open(self.db, "rb") as f:
            data = bytearray(f.read())

        pls = self._playlist_sections(data)
        track_end = (self._mhsd_track_off
                     + struct.unpack_from("<I", data, self._mhsd_track_off + 8)[0])

        _cb(f"Kopiere auf iPod… ({fsize // 1_000_000} MB)", 40)

        # Build new DB: insert mhit, then each mhip
        pls_sorted = sorted(pls, key=lambda x: x["insert_at"])
        pieces = [bytes(data[:track_end]), new_mhit]
        prev = track_end
        for ps in pls_sorted:
            pieces.append(bytes(data[prev:ps["insert_at"]]))
            pieces.append(self._mhip(new_id, dbid_lo, dbid_hi, ts, ps["last_seq"] + 1))
            prev = ps["insert_at"]
        pieces.append(bytes(data[prev:]))
        new_db = bytearray(b"".join(pieces))

        mhit_sz = len(new_mhit)
        mhip_sz = 120

        # Update mhlt num_tracks (+8)
        struct.pack_into("<I", new_db, self._mhlt_off + 8,
                         struct.unpack_from("<I", new_db, self._mhlt_off + 8)[0] + 1)
        # Update mhsd track total
        struct.pack_into("<I", new_db, self._mhsd_track_off + 8,
                         struct.unpack_from("<I", new_db, self._mhsd_track_off + 8)[0] + mhit_sz)
        # Update each playlist section (shifted by mhit_sz + prior mhip insertions)
        # NOTE: mhyp+12 (children) counts mhod metadata records only — do NOT touch it.
        # Only update mhsd total, mhyp total, and mhyp tracks (+16).
        shift = mhit_sz
        for ps in pls_sorted:
            for fld in ("mhsd_total_off", "mhyp_total_off"):
                off = ps[fld] + shift
                struct.pack_into("<I", new_db, off,
                                 struct.unpack_from("<I", new_db, off)[0] + mhip_sz)
            struct.pack_into("<I", new_db, ps["mhyp_tr_off"] + shift,
                             struct.unpack_from("<I", new_db, ps["mhyp_tr_off"] + shift)[0] + 1)
            shift += mhip_sz
        # Update mhbd total
        struct.pack_into("<I", new_db, self._mhbd_total_off, len(new_db))

        assert new_db[:4] == b"mhbd"
        assert struct.unpack_from("<I", new_db, self._mhbd_total_off)[0] == len(new_db)

        guid = _get_firewire_guid(self.path)
        if guid:
            _hash58_sign(new_db, guid)

        shutil.copy2(self.db, self.db + ".bak")
        shutil.copy2(audio_path, dest)

        _cb("Schreibe Datenbank…", 90)
        with open(self.db, "wb") as f:
            f.write(new_db)
        self._data = new_db

        _cb("Fertig!", 100)
        return dict(id=new_id, title=title, artist=artist, album=album,
                    genre=genre, duration_ms=dur_ms, file_size=fsize,
                    bitrate=brate, year=year, filename=ipod_path)

    # ----------------------------------------------------------- remove track
    def remove_track(self, track_id, progress_cb=None):
        """Remove track by ID, delete its file, update database."""
        def _cb(msg, pct):
            if progress_cb:
                progress_cb(msg, pct)

        target = next((t for t in self._tracks_raw if t[3] == track_id), None)
        if not target:
            raise ValueError(f"Track {track_id} nicht gefunden")
        off, hdr, total, _ = target

        data = self._data
        dbid_lo = struct.unpack_from("<I", data, off + 112)[0]
        dbid_hi = struct.unpack_from("<I", data, off + 116)[0]

        # Get audio filename from mhod type=2
        filename = None
        mo = off + hdr
        while mo < off + total:
            if data[mo:mo + 4] != b"mhod":
                break
            m_total = struct.unpack_from("<I", data, mo + 8)[0]
            if struct.unpack_from("<I", data, mo + 12)[0] == 2:
                slen = struct.unpack_from("<I", data, mo + 28)[0]
                filename = data[mo + 40:mo + 40 + slen].decode("utf-16-le").rstrip("\x00")
            mo += m_total

        _cb("Suche Playlist-Einträge…", 20)
        pls = self._playlist_sections(data)

        # Collect all bytes ranges to remove: (offset, size)
        removes = [(off, total)]  # mhit
        for ps in pls:
            mhyp_pos = ps["mhyp_total_off"] - 8
            mhyp_hdr_sz = struct.unpack_from("<I", data, mhyp_pos + 4)[0]
            mhyp_total = struct.unpack_from("<I", data, mhyp_pos + 8)[0]
            c = mhyp_pos + mhyp_hdr_sz
            end = mhyp_pos + mhyp_total
            while c < end:
                tag = data[c:c + 4]
                if tag == b"mhip":
                    c_total = struct.unpack_from("<I", data, c + 8)[0]
                    if struct.unpack_from("<I", data, c + 24)[0] == track_id:
                        removes.append((c, c_total))
                    c += c_total
                elif tag == b"mhod":
                    c += struct.unpack_from("<I", data, c + 8)[0]
                else:
                    break

        _cb("Baue neue Datenbank…", 40)
        # Remove from highest offset downward
        removes_sorted_desc = sorted(removes, key=lambda x: x[0], reverse=True)
        new_db = bytearray(data)
        for (r_off, r_sz) in removes_sorted_desc:
            del new_db[r_off:r_off + r_sz]

        # Compute adjusted offsets (after all removals)
        removes_asc = sorted(removes, key=lambda x: x[0])

        def adj(orig):
            shift = sum(sz for (ro, sz) in removes_asc if ro < orig)
            return orig - shift

        # mhlt num_tracks
        mf = adj(self._mhlt_off) + 8
        struct.pack_into("<I", new_db, mf,
                         struct.unpack_from("<I", new_db, mf)[0] - 1)
        # mhsd track total
        sf = adj(self._mhsd_track_off) + 8
        struct.pack_into("<I", new_db, sf,
                         struct.unpack_from("<I", new_db, sf)[0] - total)
        # Playlist size fields (only mhsd/mhyp total and mhyp tracks — not children)
        for ps in pls:
            mhip_removes_in_section = [r for r in removes[1:]
                                        if r[0] >= ps["mhsd_total_off"]
                                        and r[0] < ps["mhsd_total_off"] + 200000]
            if not mhip_removes_in_section:
                continue
            sz_rem = sum(r[1] for r in mhip_removes_in_section)
            cnt = len(mhip_removes_in_section)
            for fld in ("mhsd_total_off", "mhyp_total_off"):
                f = adj(ps[fld])
                struct.pack_into("<I", new_db, f,
                                 struct.unpack_from("<I", new_db, f)[0] - sz_rem)
            f = adj(ps["mhyp_tr_off"])
            struct.pack_into("<I", new_db, f,
                             struct.unpack_from("<I", new_db, f)[0] - cnt)
        # mhbd total
        struct.pack_into("<I", new_db, self._mhbd_total_off, len(new_db))

        guid = _get_firewire_guid(self.path)
        if guid:
            _hash58_sign(new_db, guid)

        _cb("Schreibe Datenbank…", 70)
        shutil.copy2(self.db, self.db + ".bak")
        with open(self.db, "wb") as f:
            f.write(new_db)
        self._data = new_db

        # Delete audio file
        if filename:
            parts = filename.lstrip(":").split(":")
            fpath = os.path.join(self.path, *parts)
            if os.path.exists(fpath):
                os.remove(fpath)

        _cb("Fertig!", 100)
        return True

    # ------------------------------------------------------- disk space info
    def free_space_gb(self):
        stat = shutil.disk_usage(self.path)
        return stat.free / 1_000_000_000
