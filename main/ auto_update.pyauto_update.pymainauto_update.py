# -*- coding: utf-8 -*-
"""
=====================================================================
auto_update.py
โมดูลสำหรับฝังเข้าไปใน "โปรแกรมหลัก" เพื่อให้โปรแกรมหลักสามารถ
ตรวจสอบและติดตั้งอัพเดทที่ถูกเผยแพร่โดย "โปรแกรมแอดมิน" ได้เอง
โดยไม่ต้องพึ่ง git / github โดยตรงตอนรันจริง (อ่านแค่ไฟล์ manifest
ที่แอดมินเผยแพร่ไว้บน GitHub raw เท่านั้น)

วิธีใช้ (ห้ามแก้ GUI/ฟังก์ชันเดิมของโปรแกรมหลัก แค่เพิ่ม 3 บรรทัดนี้):

    from auto_update import AutoUpdater

    # ...ในเมธอด __init__ ของ CensorApp หลังสร้าง UI เสร็จแล้ว...
    self.updater = AutoUpdater(
        app_dir=APP_DIR,
        current_version="1.0.0",          # เวอร์ชันปัจจุบันของไฟล์นี้
        manifest_url=(
            "https://raw.githubusercontent.com/"
            "suriwrrnkulchang-art/master/main/update_manifest.json"
        ),
        parent_window=self.root,
        log_fn=self.log,
    )
    self.root.after(2000, self.updater.check_in_background)

ไม่ต้องทำอะไรมากกว่านี้ — AutoUpdater จะจัดการ popup, โหลดไฟล์,
สำรองไฟล์เดิม (.bak) และรีสตาร์ทโปรแกรมให้เองทั้งหมด
=====================================================================
"""

import os
import sys
import json
import shutil
import hashlib
import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import requests
except ImportError:
    requests = None

COLOR_BG = "#101820"
COLOR_PANEL = "#182430"
COLOR_ACCENT = "#3ddc97"
COLOR_ACCENT_DARK = "#25a877"
COLOR_TEXT = "#e7edf3"
COLOR_TEXT_MUTED = "#93a2b3"
COLOR_DANGER = "#ff6b6b"
COLOR_BORDER = "#2a3947"

VERSION_FILE_NAME = "version_info.json"
REQUEST_TIMEOUT = 15


def _version_tuple(v):
    """แปลง '1.2.3' -> (1, 2, 3) เพื่อเทียบเวอร์ชันแบบตัวเลข ไม่ใช่ตัวอักษร"""
    parts = []
    for p in str(v).strip().split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class AutoUpdater:
    """
    ตรวจสอบ manifest บน GitHub (raw) แล้วถามผู้ใช้ก่อนติดตั้งอัพเดท
    manifest ต้องมีรูปแบบ:
    {
        "app_name": "SKYFILM Voice Censor",
        "version": "1.1.0",
        "changelog": "รายละเอียดการอัพเดท...",
        "published_at": "2026-07-05T12:00:00",
        "files": [
            {
                "path": "voice_censor.py",   # path สัมพัทธ์ในโฟลเดอร์โปรแกรมหลัก
                "sha256": "....",
                "raw_url": "https://raw.githubusercontent.com/.../voice_censor.py"
            }
        ]
    }
    """

    def __init__(self, app_dir, current_version, manifest_url,
                 parent_window=None, log_fn=None, version_file_name=VERSION_FILE_NAME):
        self.app_dir = app_dir
        self.manifest_url = manifest_url
        self.parent = parent_window
        self.log = log_fn if log_fn else (lambda msg: None)
        self.version_file_path = os.path.join(app_dir, version_file_name)
        self.current_version = self._load_local_version(default=current_version)
        self._checking = False

    # ------------------------------------------------------------------ #
    def _load_local_version(self, default):
        if os.path.exists(self.version_file_path):
            try:
                with open(self.version_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                v = data.get("version")
                if v:
                    return v
            except Exception:
                pass
        return default

    def _save_local_version(self, version, changelog=""):
        data = {"version": version, "changelog": changelog}
        try:
            with open(self.version_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def check_in_background(self):
        """เรียกจาก main thread (เช่นผ่าน root.after) — จะไปเช็คใน thread แยก"""
        if self._checking:
            return
        if requests is None:
            self.log("⚠ ไม่พบไลบรารี requests จึงตรวจสอบอัพเดทไม่ได้ (pip install requests)")
            return
        self._checking = True
        t = threading.Thread(target=self._check_worker, daemon=True)
        t.start()

    def _check_worker(self):
        try:
            manifest = self._fetch_manifest()
        except Exception as e:
            self.log(f"ตรวจสอบอัพเดทไม่สำเร็จ (เช็คอินเทอร์เน็ต): {e}")
            self._checking = False
            return

        self._checking = False
        if manifest is None:
            return

        remote_version = manifest.get("version", "0.0.0")
        if _version_tuple(remote_version) <= _version_tuple(self.current_version):
            self.log(f"เช็คอัพเดทแล้ว: ใช้เวอร์ชันล่าสุดอยู่แล้ว ({self.current_version})")
            return

        self.log(f"🔔 พบเวอร์ชันใหม่ {remote_version} (ปัจจุบัน {self.current_version})")

        # ต้องเด้ง popup บน main thread ของ Tk เท่านั้น
        if self.parent is not None:
            self.parent.after(0, lambda: self._show_update_popup(manifest))
        else:
            self._show_update_popup(manifest)

    def _fetch_manifest(self):
        resp = requests.get(self.manifest_url, timeout=REQUEST_TIMEOUT,
                             headers={"Cache-Control": "no-cache"})
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}")
        return resp.json()

    # ------------------------------------------------------------------ #
    def _show_update_popup(self, manifest):
        win = tk.Toplevel(self.parent) if self.parent else tk.Tk()
        win.title("มีอัพเดทใหม่")
        win.configure(bg=COLOR_PANEL)
        win.geometry("480x420")
        win.resizable(False, False)
        win.grab_set()
        if self.parent:
            win.transient(self.parent)

        pad = {"padx": 18, "pady": 6}

        tk.Label(win, text="🔔 พบเวอร์ชันใหม่!", bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=("Tahoma", 15, "bold")).pack(anchor="w", **pad)

        name = manifest.get("app_name", "โปรแกรมหลัก")
        version = manifest.get("version", "-")
        published = manifest.get("published_at", "-")

        info_frame = tk.Frame(win, bg=COLOR_PANEL)
        info_frame.pack(fill="x", padx=18)
        tk.Label(info_frame, text=f"โปรแกรม: {name}", bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Tahoma", 10, "bold")).pack(anchor="w")
        tk.Label(info_frame, text=f"เวอร์ชันใหม่: {version}   (เดิม {self.current_version})",
                 bg=COLOR_PANEL, fg=COLOR_TEXT).pack(anchor="w", pady=(2, 0))
        tk.Label(info_frame, text=f"เผยแพร่เมื่อ: {published}",
                 bg=COLOR_PANEL, fg=COLOR_TEXT_MUTED).pack(anchor="w")

        tk.Label(win, text="รายละเอียดการอัพเดท:", bg=COLOR_PANEL, fg=COLOR_ACCENT,
                 font=("Tahoma", 10, "bold")).pack(anchor="w", padx=18, pady=(12, 2))

        text_frame = tk.Frame(win, bg=COLOR_PANEL)
        text_frame.pack(fill="both", expand=True, padx=18)
        changelog_box = tk.Text(text_frame, wrap="word", bg="#1f2e3c", fg=COLOR_TEXT,
                                 relief="flat", height=8, borderwidth=0)
        changelog_box.insert("1.0", manifest.get("changelog", "(ไม่มีรายละเอียด)"))
        changelog_box.config(state="disabled")
        changelog_box.pack(fill="both", expand=True)

        btn_frame = tk.Frame(win, bg=COLOR_PANEL)
        btn_frame.pack(fill="x", padx=18, pady=16)

        def on_accept():
            win.destroy()
            self._run_update_flow(manifest)

        def on_decline():
            win.destroy()
            self.log("ผู้ใช้เลือกไม่ติดตั้งอัพเดทในตอนนี้")

        tk.Button(btn_frame, text="✔  ตกลง อัพเดทเลย", bg=COLOR_ACCENT, fg="#062018",
                  font=("Tahoma", 10, "bold"), relief="flat", padx=14, pady=8,
                  activebackground=COLOR_ACCENT_DARK, command=on_accept).pack(side="left")
        tk.Button(btn_frame, text="✘  ไม่ตกลง", bg=COLOR_BORDER, fg=COLOR_TEXT,
                  font=("Tahoma", 10), relief="flat", padx=14, pady=8,
                  command=on_decline).pack(side="right")

    # ------------------------------------------------------------------ #
    def _run_update_flow(self, manifest):
        win = tk.Toplevel(self.parent) if self.parent else tk.Tk()
        win.title("กำลังอัพเดท...")
        win.configure(bg=COLOR_PANEL)
        win.geometry("420x160")
        win.resizable(False, False)
        win.grab_set()
        if self.parent:
            win.transient(self.parent)

        status_var = tk.StringVar(value="กำลังเตรียมการอัพเดท...")
        tk.Label(win, textvariable=status_var, bg=COLOR_PANEL, fg=COLOR_TEXT,
                 font=("Tahoma", 11)).pack(pady=(24, 10))

        progress = ttk.Progressbar(win, mode="determinate", length=340)
        progress.pack(pady=6)

        detail_var = tk.StringVar(value="")
        tk.Label(win, textvariable=detail_var, bg=COLOR_PANEL, fg=COLOR_TEXT_MUTED,
                 font=("Tahoma", 9)).pack()

        def worker():
            files = manifest.get("files", [])
            total = max(1, len(files))
            backups = []
            try:
                for i, entry in enumerate(files, start=1):
                    rel_path = entry["path"]
                    raw_url = entry["raw_url"]
                    expected_sha = entry.get("sha256")

                    win.after(0, lambda p=rel_path, i=i, t=total: (
                        status_var.set(f"กำลังดาวน์โหลด ({i}/{t})"),
                        detail_var.set(p),
                    ))

                    r = requests.get(raw_url, timeout=REQUEST_TIMEOUT)
                    if r.status_code != 200:
                        raise RuntimeError(f"ดาวน์โหลด {rel_path} ไม่สำเร็จ (HTTP {r.status_code})")
                    content = r.content

                    if expected_sha:
                        got_sha = hashlib.sha256(content).hexdigest()
                        if got_sha != expected_sha:
                            raise RuntimeError(f"ไฟล์ {rel_path} เช็คซัมไม่ตรง (ไฟล์อาจเสียหาย)")

                    dest_path = os.path.join(self.app_dir, rel_path)
                    os.makedirs(os.path.dirname(dest_path) or self.app_dir, exist_ok=True)

                    if os.path.exists(dest_path):
                        bak_path = dest_path + ".bak"
                        shutil.copy2(dest_path, bak_path)
                        backups.append((dest_path, bak_path))

                    with open(dest_path, "wb") as f:
                        f.write(content)

                    win.after(0, lambda i=i, t=total: progress.config(value=(i / t) * 100))

                self._save_local_version(manifest.get("version"), manifest.get("changelog", ""))
                self.current_version = manifest.get("version")

                win.after(0, lambda: status_var.set("อัพเดทสำเร็จ! กำลังรีสตาร์ทโปรแกรม..."))
                win.after(1200, lambda: self._restart_app(win))

            except Exception as e:
                err_text = str(e)
                self.log("อัพเดทล้มเหลว: " + traceback.format_exc())
                # กู้คืนไฟล์เดิมกลับมาถ้าอัพเดทล้มเหลวระหว่างทาง
                for dest_path, bak_path in backups:
                    try:
                        shutil.copy2(bak_path, dest_path)
                    except Exception:
                        pass
                win.after(0, lambda: self._show_update_failed(win, err_text))

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_failed(self, win, err_text):
        win.destroy()
        messagebox.showerror("อัพเดทไม่สำเร็จ",
                              f"เกิดข้อผิดพลาดระหว่างอัพเดท:\n{err_text}\n\n"
                              f"ไฟล์เดิมถูกกู้คืนเรียบร้อยแล้ว โปรแกรมยังใช้งานได้ตามปกติ")

    def _restart_app(self, win):
        win.destroy()
        try:
            python = sys.executable
            os.execv(python, [python] + sys.argv)
        except Exception:
            messagebox.showinfo("อัพเดทเสร็จสิ้น", "กรุณาปิดและเปิดโปรแกรมใหม่อีกครั้งเพื่อใช้เวอร์ชันล่าสุด")
