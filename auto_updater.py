#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
 auto_updater.py — โมดูลฝังในโปรแกรมหลัก สำหรับตรวจสอบ/ติดตั้งอัพเดท
=====================================================================
ใช้งานคู่กับ admin_updater.py

หลักการทำงาน:
- admin_updater.py จะเป็นคนตรวจสอบ GitHub, ตรวจบัค, และ "เผยแพร่" แพ็กเกจ
  อัพเดทไปไว้ในโฟลเดอร์ที่เรียกว่า "Update Channel" (โฟลเดอร์ที่ทั้งแอดมิน
  และเครื่องผู้ใช้ทุกเครื่องมองเห็นร่วมกัน เช่น โฟลเดอร์แชร์ในเครือข่าย,
  Google Drive Desktop, Dropbox, OneDrive ฯลฯ)
- โปรแกรมหลัก (ที่ import โมดูลนี้) จะไม่ต้องต่อ GitHub เองเลย
  แค่คอยเช็คไฟล์ manifest.json ใน Update Channel เป็นระยะ ๆ
- เมื่อพบเวอร์ชันใหม่กว่าเวอร์ชันที่ติดตั้งอยู่ -> เด้งป็อปอัพถามผู้ใช้
  -> กด "ตกลง" -> โชว์หน้าโหลด -> คัดลอกไฟล์ใหม่ทับของเดิม (สำรองของเก่าไว้ก่อน)
  -> รีสตาร์ทโปรแกรมให้อัตโนมัติ

การเรียกใช้ในโปรแกรมหลัก (เพิ่มแค่ 2-3 บรรทัด ไม่ต้องแก้ GUI/ฟังก์ชันเดิม):

    import auto_updater

    updater = auto_updater.AutoUpdater(
        root=root,                      # tk.Tk() ของโปรแกรมหลัก
        app_name="SKYFILM Voice Censor",
        current_version="Beta 1.0",
        channel_dir=r"C:\\SharedUpdateChannel",   # ต้องตรงกับที่ตั้งใน admin_updater.py
    )
    updater.start()

โมดูลนี้ไม่มี dependency พิเศษ ใช้แต่ของที่มากับ Python มาตรฐาน
(tkinter, threading, json, shutil, os)
"""

import os
import sys
import json
import time
import shutil
import threading
import traceback
from datetime import datetime

import tkinter as tk
from tkinter import ttk


# ------------------------------------------------------------------ ธีมสี ---
# ธีมสีเริ่มต้น (ถ้าไม่ส่ง theme มา จะใช้ชุดนี้ ซึ่งเข้ากับธีมของโปรแกรมหลัก)
DEFAULT_THEME = {
    "bg": "#101820",
    "panel": "#182430",
    "panel_alt": "#1f2e3c",
    "accent": "#3ddc97",
    "accent_dark": "#25a877",
    "text": "#e7edf3",
    "text_muted": "#93a2b3",
    "danger": "#ff6b6b",
    "border": "#2a3947",
}

MANIFEST_NAME = "manifest.json"
LOCAL_VERSION_FILE = "version_info.json"
POLL_INTERVAL_SEC = 30  # ความถี่ในการเช็คอัพเดท (วินาที)


def _version_tuple(v):
    """แปลงสตริงเวอร์ชันเป็น tuple ตัวเลขเพื่อเทียบขนาด เช่น '1.2.10' -> (1,2,10)
    ถ้าแปลงเป็นตัวเลขไม่ได้ทั้งหมด จะ fallback ไปเทียบเป็นสตริงตรง ๆ"""
    parts = []
    for chunk in str(v).replace("-", ".").replace("_", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def _is_newer(remote_version, local_version):
    try:
        return _version_tuple(remote_version) > _version_tuple(local_version)
    except Exception:
        return str(remote_version) != str(local_version)


class AutoUpdater:
    """
    ตัวจัดการอัพเดทฝั่งไคลเอนต์ (โปรแกรมหลัก)

    Parameters
    ----------
    root : tk.Tk หรือ tk.Toplevel ของโปรแกรมหลัก (ใช้เป็น parent ของป็อปอัพ)
    app_name : ชื่อโปรแกรม (ใช้แสดงผลเท่านั้น)
    current_version : เวอร์ชันปัจจุบันที่ติดตั้งอยู่ตอนนี้
    channel_dir : พาธของ "Update Channel" โฟลเดอร์ (ต้องตรงกับ admin_updater.py)
    install_dir : โฟลเดอร์ที่จะให้ทับไฟล์ใหม่ลงไป (ค่าเริ่มต้น = โฟลเดอร์ที่ตัวโปรแกรมหลักอยู่)
    theme : dict สีธีม (ไม่ใส่ก็ได้ จะใช้ค่า default ที่เข้ากับธีมโปรแกรมหลัก)
    on_log : callback(str) เผื่ออยากต่อเข้ากับกล่อง log เดิมของโปรแกรมหลัก (ไม่ใส่ก็ได้)
    auto_restart : bool ถ้า True (ค่าเริ่มต้น) จะรีสตาร์ทโปรแกรมอัตโนมัติหลังอัพเดทเสร็จ
    """

    def __init__(self, root, app_name, current_version, channel_dir,
                 install_dir=None, theme=None, on_log=None, auto_restart=True):
        self.root = root
        self.app_name = app_name
        self.current_version = current_version
        self.channel_dir = channel_dir
        self.install_dir = install_dir or os.path.dirname(os.path.abspath(sys.argv[0]))
        self.theme = dict(DEFAULT_THEME)
        if theme:
            self.theme.update(theme)
        self.on_log = on_log or (lambda msg: None)
        self.auto_restart = auto_restart

        self._stop_flag = threading.Event()
        self._thread = None
        self._dismissed_versions = set()
        self._popup_open = False

        self._local_version_path = os.path.join(self.install_dir, LOCAL_VERSION_FILE)
        self._ensure_local_version_file()

    # -------------------------------------------------------- ไฟล์เวอร์ชันเครื่อง
    def _ensure_local_version_file(self):
        if not os.path.exists(self._local_version_path):
            self._write_local_version(self.current_version)

    def _read_local_version(self):
        try:
            with open(self._local_version_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("version", self.current_version)
        except Exception:
            return self.current_version

    def _write_local_version(self, version):
        try:
            with open(self._local_version_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"app_name": self.app_name, "version": version,
                     "updated_at": datetime.now().isoformat(timespec="seconds")},
                    f, ensure_ascii=False, indent=2,
                )
        except Exception:
            self.on_log("⚠ บันทึกไฟล์เวอร์ชันไม่สำเร็จ")

    # ------------------------------------------------------------- เธรดหลัก
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.on_log(f"🔄 เริ่มระบบตรวจสอบอัพเดทอัตโนมัติ (ทุก {POLL_INTERVAL_SEC} วินาที)")

    def stop(self):
        self._stop_flag.set()

    def _run_loop(self):
        # เช็คทันทีตอนเปิดโปรแกรม แล้วค่อยวนตามรอบเวลา
        while not self._stop_flag.is_set():
            try:
                self._check_once()
            except Exception:
                self.on_log("เกิดข้อผิดพลาดขณะตรวจสอบอัพเดท:\n" + traceback.format_exc())
            for _ in range(POLL_INTERVAL_SEC):
                if self._stop_flag.is_set():
                    return
                time.sleep(1)

    def _check_once(self):
        if not self.channel_dir or not os.path.isdir(self.channel_dir):
            return  # ยังไม่ได้ตั้งค่า / เข้าถึงโฟลเดอร์ไม่ได้ ก็ข้ามรอบนี้ไป
        manifest_path = os.path.join(self.channel_dir, MANIFEST_NAME)
        if not os.path.exists(manifest_path):
            return
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            self.on_log("⚠ อ่านไฟล์ manifest.json ไม่ได้ (อาจกำลังถูกเขียนอยู่พอดี)")
            return

        remote_version = manifest.get("version")
        if not remote_version:
            return

        local_version = self._read_local_version()
        if not _is_newer(remote_version, local_version):
            return
        if remote_version in self._dismissed_versions:
            return
        if self._popup_open:
            return

        package_dir_name = manifest.get("package_dir")
        package_dir = os.path.join(self.channel_dir, package_dir_name) if package_dir_name else None
        if not package_dir or not os.path.isdir(package_dir):
            self.on_log(f"⚠ พบ manifest เวอร์ชัน {remote_version} แต่ไม่พบไฟล์แพ็กเกจ ({package_dir_name})")
            return

        # ต้องเรียก UI (popup) บนเธรดหลักของ tkinter เท่านั้น
        self.root.after(0, lambda: self._show_update_popup(manifest, package_dir))

    # ------------------------------------------------------------- ป็อปอัพ
    def _show_update_popup(self, manifest, package_dir):
        if self._popup_open:
            return
        self._popup_open = True
        th = self.theme

        win = tk.Toplevel(self.root)
        win.title("มีอัพเดทใหม่")
        win.configure(bg=th["panel"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()

        pad = {"padx": 20, "pady": 10}

        name = manifest.get("app_name", self.app_name)
        version = manifest.get("version", "-")
        desc = manifest.get("description", "(ไม่มีรายละเอียดเพิ่มเติม)")
        released_at = manifest.get("released_at", "")

        tk.Label(win, text=f"🆕 พบอัพเดทใหม่: {name}", font=("Tahoma", 13, "bold"),
                 bg=th["panel"], fg=th["accent"]).pack(anchor="w", **pad)
        tk.Label(win, text=f"เวอร์ชันใหม่: {version}   (เวอร์ชันปัจจุบัน: {self._read_local_version()})",
                 bg=th["panel"], fg=th["text"]).pack(anchor="w", padx=20)
        if released_at:
            tk.Label(win, text=f"เผยแพร่เมื่อ: {released_at}",
                     bg=th["panel"], fg=th["text_muted"]).pack(anchor="w", padx=20, pady=(2, 8))

        tk.Label(win, text="รายละเอียดการอัพเดท:", bg=th["panel"], fg=th["accent"]).pack(anchor="w", padx=20)
        detail_box = tk.Text(win, width=54, height=8, wrap="word", bg=th["panel_alt"], fg=th["text"],
                              relief="flat", borderwidth=0)
        detail_box.insert("1.0", desc)
        detail_box.config(state="disabled")
        detail_box.pack(padx=20, pady=(2, 12))

        btn_row = tk.Frame(win, bg=th["panel"])
        btn_row.pack(pady=(0, 16))

        def on_cancel():
            self._dismissed_versions.add(version)
            self._popup_open = False
            win.destroy()

        def on_ok():
            win.destroy()
            self._popup_open = False
            self._run_update(manifest, package_dir)

        tk.Button(btn_row, text="ยกเลิก", command=on_cancel, bg=th["panel_alt"], fg=th["text"],
                  relief="flat", padx=18, pady=6).pack(side="left", padx=8)
        tk.Button(btn_row, text="ตกลง อัพเดทเลย", command=on_ok, bg=th["accent"], fg="#062018",
                  relief="flat", padx=18, pady=6, font=("Tahoma", 10, "bold")).pack(side="left", padx=8)

        win.protocol("WM_DELETE_WINDOW", on_cancel)

        # จัดตำแหน่งกลางหน้าต่างหลัก
        win.update_idletasks()
        try:
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            ww, wh = win.winfo_width(), win.winfo_height()
            win.geometry(f"+{rx + (rw - ww)//2}+{ry + (rh - wh)//2}")
        except Exception:
            pass

    # ------------------------------------------------------------- ติดตั้งอัพเดท
    def _run_update(self, manifest, package_dir):
        th = self.theme
        win = tk.Toplevel(self.root)
        win.title("กำลังอัพเดท")
        win.configure(bg=th["panel"])
        win.resizable(False, False)
        win.transient(self.root)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", lambda: None)  # กันปิดระหว่างอัพเดท

        tk.Label(win, text="⏳ กำลังติดตั้งอัพเดท กรุณารอสักครู่...", bg=th["panel"], fg=th["text"],
                 font=("Tahoma", 11)).pack(padx=30, pady=(24, 10))
        progress = ttk.Progressbar(win, mode="indeterminate", length=280)
        progress.pack(padx=30, pady=(0, 24))
        progress.start(12)
        win.update_idletasks()
        try:
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            ww, wh = win.winfo_width(), win.winfo_height()
            win.geometry(f"+{rx + (rw - ww)//2}+{ry + (rh - wh)//2}")
        except Exception:
            pass

        def do_apply():
            ok, err = self._apply_update_files(package_dir)
            self.root.after(0, lambda: finish(ok, err))

        def finish(ok, err):
            progress.stop()
            win.destroy()
            if ok:
                self._write_local_version(manifest.get("version"))
                self.on_log(f"✅ อัพเดทเป็นเวอร์ชัน {manifest.get('version')} สำเร็จแล้ว กำลังรีสตาร์ทโปรแกรม...")
                if self.auto_restart:
                    self.root.after(600, self._restart_app)
            else:
                self.on_log("❌ อัพเดทไม่สำเร็จ: " + str(err) + "\nได้กู้คืนไฟล์เดิมกลับแล้ว")

        threading.Thread(target=do_apply, daemon=True).start()

    def _apply_update_files(self, package_dir):
        """คัดลอกไฟล์จาก package_dir ทับ install_dir แบบปลอดภัย:
        สำรองไฟล์เดิมไว้ก่อน ถ้าเกิดข้อผิดพลาดระหว่างคัดลอก จะกู้คืนไฟล์เดิมกลับให้อัตโนมัติ
        """
        backup_dir = os.path.join(
            self.install_dir, f"_backup_before_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        copied_relpaths = []
        try:
            os.makedirs(backup_dir, exist_ok=True)
            for dirpath, dirnames, filenames in os.walk(package_dir):
                # ข้ามไฟล์ระบบของ git ถ้าหลงเหลือมา
                dirnames[:] = [d for d in dirnames if d != ".git"]
                for fname in filenames:
                    src_path = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(src_path, package_dir)
                    dst_path = os.path.join(self.install_dir, rel_path)

                    # สำรองไฟล์เดิม (ถ้ามี) ก่อนทับ
                    if os.path.exists(dst_path):
                        backup_path = os.path.join(backup_dir, rel_path)
                        os.makedirs(os.path.dirname(backup_path), exist_ok=True)
                        shutil.copy2(dst_path, backup_path)

                    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
                    shutil.copy2(src_path, dst_path)
                    copied_relpaths.append(rel_path)
            return True, None
        except Exception as e:
            # กู้คืนไฟล์ที่สำรองไว้ กรณีเกิดปัญหาระหว่างทาง
            try:
                for rel_path in copied_relpaths:
                    backup_path = os.path.join(backup_dir, rel_path)
                    dst_path = os.path.join(self.install_dir, rel_path)
                    if os.path.exists(backup_path):
                        shutil.copy2(backup_path, dst_path)
            except Exception:
                pass
            return False, str(e)

    def _restart_app(self):
        try:
            self.root.destroy()
        except Exception:
            pass
        python = sys.executable
        os.execv(python, [python] + sys.argv)


def attach(root, app_name, current_version, channel_dir, install_dir=None,
           theme=None, on_log=None, auto_restart=True):
    """ทางลัด: สร้างและเริ่มการทำงานของ AutoUpdater ในบรรทัดเดียว"""
    updater = AutoUpdater(
        root=root, app_name=app_name, current_version=current_version,
        channel_dir=channel_dir, install_dir=install_dir, theme=theme,
        on_log=on_log, auto_restart=auto_restart,
    )
    updater.start()
    return updater
