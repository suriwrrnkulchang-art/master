#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=====================================================================
โปรแกรมเซ็นเซอร์คำไม่สุภาพแบบเรียลไทม์ (Real-time Profanity Censor)
เวอร์ชันปรับปรุง: SpeechRecognition + PyAudio (Google Web Speech API)

สิ่งที่เพิ่มจากเวอร์ชันเดิม:
  - ฟังและตรวจจับคำหยาบแบบต่อเนื่อง (ปรับ pause_threshold / phrase_time_limit
    ให้สั้นลง) ทำให้พูดต่อเนื่องได้และเซ็นเซอร์ทันเมื่อเจอคำหยาบ แล้วเสียง
    ปกติหลังจากนั้นจะไม่ถูกเซ็นเซอร์ต่อ (เซ็นเซอร์เฉพาะช่วงที่เจอคำหยาบจริง)
  - บันทึกค่าที่ตั้งไว้ทั้งหมดอัตโนมัติทันทีที่มีการเปลี่ยนแปลง (ไมโครโฟน,
    เอาต์พุต, ภาษา, ค่าหน่วงเวลา, ความไว, รายการคำหยาบ ฯลฯ) โดยไม่ต้องกด
    ปุ่มบันทึกเอง แล้วโหลดค่าที่บันทึกไว้กลับมาอัตโนมัติทุกครั้งที่เปิดโปรแกรม
  - ระบบเริ่มโปรแกรมอัตโนมัติเมื่อเปิดเครื่อง (Windows) เปิด/ปิดได้จากหน้า
    "ตั้งค่า" (ใช้ Registry Run key)
  - ตัวเลือก "เริ่มเซ็นเซอร์ทันทีเมื่อเปิดโปรแกรม" แยกต่างหากจากการเริ่ม
    โปรแกรมตอนบูตเครื่อง
  - จัดหมวดหมู่ UI เป็นแท็บ: "อุปกรณ์ & คำหยาบ" และ "ตั้งค่า"

วิธีติดตั้ง (รันใน Command Prompt / Terminal ก่อนเปิดโปรแกรม):

    pip install SpeechRecognition PyAudio numpy soundfile

หมายเหตุการติดตั้ง PyAudio:
  - Windows: ปกติ "pip install PyAudio" ใช้ได้เลย ถ้าติดตั้งไม่ผ่าน ให้ลอง
        pip install pipwin
        pipwin install pyaudio
  - macOS:  ต้องมี portaudio ก่อน -> brew install portaudio  แล้วค่อย pip install pyaudio
  - Linux:  sudo apt install portaudio19-dev python3-pyaudio  แล้วค่อย pip install pyaudio

เวอร์ชันนี้ใช้ Google Web Speech API (ฟรี, ผ่าน SpeechRecognition) ในการแปลงเสียงเป็นข้อความ
ซึ่ง "ต้องต่ออินเทอร์เน็ต" และมีความหน่วง (ต้องรอพูดจบประโยค + ส่งไปประมวลผลที่เซิร์ฟเวอร์)
มากกว่าการรู้จำเสียงแบบออฟไลน์ ดังนั้นโปรแกรมนี้จะ "หน่วงเสียงเอาต์พุต" ไว้ล่วงหน้าสักครู่
(ตั้งค่าได้) เพื่อให้มีเวลาพอสำหรับผลลัพธ์จาก Google กลับมาก่อนที่เสียงส่วนนั้นจะถูกส่งออกจริง

ถ้าต้องการส่งเสียงที่เซ็นเซอร์แล้วเข้าไปใช้ใน Discord หรือเกม (ใช้กับแอปอื่นได้):
    1. ติดตั้งโปรแกรม Virtual Audio Cable ฟรี เช่น "VB-CABLE"
       (ดาวน์โหลดที่ https://vb-audio.com/Cable/ )
    2. เปิดโปรแกรมนี้ แล้วเลือก "อุปกรณ์เอาต์พุต (Output)" เป็น "CABLE Input"
    3. ไปที่ Discord/เกม แล้วตั้งค่าไมโครโฟน (Input Device) ให้เป็น "CABLE Output"

หมายเหตุระบบ "เริ่มอัตโนมัติเมื่อเปิดเครื่อง":
  - รองรับเฉพาะ Windows (ใช้ Registry: HKEY_CURRENT_USER\\...\\Run)
  - ถ้ารันเป็นไฟล์ .py ธรรมดา โปรแกรมจะสร้างคำสั่งเรียก pythonw.exe + พาธไฟล์นี้
  - ถ้าคอมไพล์เป็น .exe (เช่นด้วย PyInstaller) โปรแกรมจะเรียก .exe โดยตรง
=====================================================================
"""

import os
import sys
import json
import queue
import threading
import traceback
from collections import deque

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ---------------------------------------------------------------------------
# ตรวจสอบไลบรารีที่จำเป็น (import แบบปลอดภัย จะได้แจ้งผู้ใช้ได้ชัดเจนถ้าขาดอะไร)
# ---------------------------------------------------------------------------
MISSING_LIBS = []

try:
    import numpy as np
except ImportError:
    np = None
    MISSING_LIBS.append("numpy")

try:
    import pyaudio
except ImportError:
    pyaudio = None
    MISSING_LIBS.append("PyAudio")

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    MISSING_LIBS.append("SpeechRecognition")

try:
    import soundfile as sf
except ImportError:
    sf = None  # ไม่บังคับ ใช้ได้แค่ฟีเจอร์โหลดไฟล์เสียงกำหนดเอง

IS_WINDOWS = (os.name == "nt")
if IS_WINDOWS:
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None


APP_DIR = os.path.dirname(os.path.abspath(__file__))
WORDS_FILE = os.path.join(APP_DIR, "bad_words.json")
SETTINGS_FILE = os.path.join(APP_DIR, "censor_settings_sr.json")

APP_REG_NAME = "VoiceProfanityCensor"
STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

SAMPLE_RATE = 16000
BLOCK_SEC = 0.1                         # ความยาวของแต่ละ block เสียง (วินาที)
BLOCK_SIZE = int(SAMPLE_RATE * BLOCK_SEC)   # จำนวนตัวอย่างเสียงต่อ block (1600)

LANGUAGE_OPTIONS = [
    ("ไทย (th-TH)", "th-TH"),
    ("อังกฤษ US (en-US)", "en-US"),
    ("อังกฤษ UK (en-GB)", "en-GB"),
]

DEFAULT_SETTINGS = {
    "delay_seconds": 4.0,
    "mute_seconds": 2.5,
    "out_channels": 2,
    "language": "th-TH",
    "pause_threshold": 0.5,      # ยิ่งน้อย ยิ่งตัดประโยคเร็ว = ตรวจจับต่อเนื่องขึ้น
    "phrase_time_limit": 4.0,    # ความยาวสูงสุดต่อประโยคที่ส่งไปรู้จำ
    "input_device_index": None,
    "input_device_name": "",
    "output_device_index": None,
    "output_device_name": "",
    "auto_start_windows": False,
    "auto_start_engine": False,
}


# ===========================================================================
# ระบบเริ่มโปรแกรมอัตโนมัติเมื่อเปิดเครื่อง (Windows Registry Run key)
# ===========================================================================
def _startup_command():
    """สร้างคำสั่งที่จะใช้เรียกโปรแกรมนี้ตอนเปิดเครื่อง"""
    if getattr(sys, "frozen", False):
        # กรณีถูกคอมไพล์เป็น .exe ด้วย PyInstaller เป็นต้น
        return f'"{sys.executable}"'
    exe = sys.executable
    pythonw = exe.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = exe
    script_path = os.path.abspath(__file__)
    return f'"{pythonw}" "{script_path}"'


def set_windows_startup(enable: bool):
    if not IS_WINDOWS or winreg is None:
        raise RuntimeError("ระบบเริ่มอัตโนมัติเมื่อเปิดเครื่องรองรับเฉพาะ Windows เท่านั้น")
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_SET_VALUE)
    try:
        if enable:
            winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, APP_REG_NAME)
            except FileNotFoundError:
                pass
    finally:
        winreg.CloseKey(key)


def is_windows_startup_enabled():
    if not IS_WINDOWS or winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, APP_REG_NAME)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


# ===========================================================================
# ส่วนประมวลผลเสียง / ตรวจจับคำ (Engine)
# ===========================================================================
class CensorEngine:
    """
    ทำงาน 2 อย่างคู่ขนานกัน:
      1) Passthrough: อ่านเสียงจากไมค์ -> หน่วงเวลาไว้ในบัฟเฟอร์ -> ส่งออกไปยังอุปกรณ์เอาต์พุต
         (ใช้ PyAudio stream สองเส้นทาง คือ input stream กับ output stream)
      2) Recognition: ใช้ SpeechRecognition (sr.Microphone + listen_in_background)
         ฟังเสียงจากไมค์ตัวเดียวกัน (เปิดอีก stream หนึ่งแยกต่างหาก) ส่งไป Google Web Speech API
         พอได้ข้อความ ตรวจว่ามีคำไม่สุภาพไหม ถ้ามี -> สั่งให้ engine ข้อ 1 เซ็นเซอร์เสียงย้อนหลัง
         เฉพาะช่วงที่เจอคำหยาบเท่านั้น ส่วนคำถัดไปที่ไม่หยาบจะไม่ถูกเซ็นเซอร์ต่อ
    """

    def __init__(self, log_fn):
        self.log = log_fn
        self.running = False

        self.pa = None                      # pyaudio.PyAudio() instance
        self.in_stream = None
        self.out_stream = None

        self.buffer_lock = threading.Lock()
        self.delay_buffer = deque()         # เก็บ numpy int16 array (1 block ต่อ 1 ก้อน)
        self.delay_blocks = 40

        self.out_channels = 2

        self.bad_words = []
        self.mute_seconds = 2.5
        self.delay_seconds = 4.0
        self.language = "th-TH"
        self.pause_threshold = 0.5
        self.phrase_time_limit = 4.0

        self.censor_wave = self._generate_beep()   # numpy int16 array
        self.censor_file_path = None

        # ---- นับสถิติ ----
        self.total_words_detected = 0

        # ส่วนของ speech_recognition
        self.recognizer = None
        self.mic_source = None
        self.stop_listening_fn = None

    # ---------------- เสียงปี๊บ default ----------------
    def _generate_beep(self, freq=1000.0, duration=0.35, volume=0.55):
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
        wave_data = (volume * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
        return wave_data

    def load_censor_file(self, path):
        """โหลดไฟล์เสียงที่ผู้ใช้เลือกมาใช้เป็นเสียงเซ็นเซอร์ (รองรับ wav/flac/ogg ผ่าน soundfile)"""
        if sf is None:
            raise RuntimeError("ต้องติดตั้งไลบรารี soundfile ก่อน (pip install soundfile)")
        data, orig_sr = sf.read(path, dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        if orig_sr != SAMPLE_RATE:
            data = self._resample(data, orig_sr, SAMPLE_RATE)
        int16_data = np.clip(data * 32767, -32768, 32767).astype(np.int16)
        self.censor_wave = int16_data
        self.censor_file_path = path

    @staticmethod
    def _resample(data, orig_sr, target_sr):
        if orig_sr == target_sr or len(data) == 0:
            return data
        duration = len(data) / float(orig_sr)
        target_len = max(1, int(duration * target_sr))
        x_old = np.linspace(0, duration, num=len(data))
        x_new = np.linspace(0, duration, num=target_len)
        return np.interp(x_new, x_old, data).astype(np.float32)

    def preview_censor_sound(self):
        """เล่นเสียงตัวอย่างเซ็นเซอร์ผ่านลำโพง default (ใช้ pyaudio ชั่วคราว)"""
        pa = pyaudio.PyAudio()
        try:
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, output=True)
            stream.write(self.censor_wave.tobytes())
            stream.stop_stream()
            stream.close()
        finally:
            pa.terminate()

    def _get_censor_samples(self, num_samples):
        wave_arr = self.censor_wave
        if wave_arr is None or len(wave_arr) == 0:
            return np.zeros(num_samples, dtype=np.int16)
        reps = int(np.ceil(num_samples / len(wave_arr))) + 1
        tiled = np.tile(wave_arr, reps)[:num_samples]
        return tiled.astype(np.int16)

    # ---------------- คำไม่สุภาพ ----------------
    def set_bad_words(self, words):
        self.bad_words = [w.strip() for w in words if w.strip()]

    # ---------------- เซ็นเซอร์เสียงย้อนหลังในบัฟเฟอร์ ----------------
    def censor_recent(self, seconds):
        """เซ็นเซอร์เฉพาะช่วงเวลาล่าสุด (ที่ตรงกับตอนพูดคำหยาบ) เท่านั้น
        เสียงก่อนหน้าและหลังจากนี้ (คำที่ไม่หยาบ) จะไม่โดนเซ็นเซอร์ต่อ"""
        blocks_to_mute = max(1, int(round(seconds / BLOCK_SEC)))
        with self.buffer_lock:
            items = list(self.delay_buffer)
            n = len(items)
            blocks_to_mute = min(blocks_to_mute, n)
            if blocks_to_mute <= 0:
                return
            total_samples = blocks_to_mute * BLOCK_SIZE
            censor_audio = self._get_censor_samples(total_samples)
            start = n - blocks_to_mute
            idx = 0
            for i in range(start, n):
                items[i] = censor_audio[idx:idx + BLOCK_SIZE]
                idx += BLOCK_SIZE
            self.delay_buffer.clear()
            self.delay_buffer.extend(items)

    # ---------------- ตรวจข้อความว่ามีคำไม่สุภาพไหม ----------------
    def _check_text(self, text):
        if not text:
            return
        hit_any = False
        hit_words = []
        for bw in self.bad_words:
            if not bw:
                continue
            if bw in text:
                hit_any = True
                hit_words.append(bw)
        if hit_any:
            self.total_words_detected += len(hit_words)
            self.log(f"⚠ ตรวจพบคำไม่สุภาพ [{', '.join(hit_words)}] -> เซ็นเซอร์ย้อนหลัง {self.mute_seconds:.1f} วิ")
            self.censor_recent(self.mute_seconds)

    # ---------------- PyAudio callbacks (ทำงานบน audio thread ของ PortAudio) ----------------
    def _input_callback(self, in_data, frame_count, time_info, status):
        try:
            arr = np.frombuffer(in_data, dtype=np.int16).copy()
            if len(arr) != BLOCK_SIZE:
                fixed = np.zeros(BLOCK_SIZE, dtype=np.int16)
                n = min(len(arr), BLOCK_SIZE)
                fixed[:n] = arr[:n]
                arr = fixed
            with self.buffer_lock:
                self.delay_buffer.append(arr)
        except Exception:
            self.log("เกิดข้อผิดพลาดใน input callback:\n" + traceback.format_exc())
        return (None, pyaudio.paContinue)

    def _output_callback(self, in_data, frame_count, time_info, status):
        try:
            with self.buffer_lock:
                if len(self.delay_buffer) > self.delay_blocks:
                    block = self.delay_buffer.popleft()
                else:
                    block = np.zeros(frame_count, dtype=np.int16)
            if len(block) != frame_count:
                fixed = np.zeros(frame_count, dtype=np.int16)
                n = min(len(block), frame_count)
                fixed[:n] = block[:n]
                block = fixed
            if self.out_channels > 1:
                out_arr = np.repeat(block.reshape(-1, 1), self.out_channels, axis=1).flatten()
            else:
                out_arr = block
            return (out_arr.tobytes(), pyaudio.paContinue)
        except Exception:
            self.log("เกิดข้อผิดพลาดใน output callback:\n" + traceback.format_exc())
            silence = np.zeros(frame_count * self.out_channels, dtype=np.int16)
            return (silence.tobytes(), pyaudio.paContinue)

    # ---------------- speech_recognition callback (ทำงานบน thread ที่ library สร้างให้) ----------------
    def _on_phrase_recognized(self, recognizer, audio):
        if not self.running:
            return
        try:
            text = recognizer.recognize_google(audio, language=self.language)
            self.log(f"🎤 ได้ยิน: {text}")
            self._check_text(text)
        except sr.UnknownValueError:
            pass  # ฟังไม่ออก/เงียบ ไม่ต้อง log กันรก
        except sr.RequestError as e:
            self.log(f"เชื่อมต่อ Google Speech API ไม่ได้ (เช็คอินเทอร์เน็ต): {e}")
        except Exception:
            self.log("เกิดข้อผิดพลาดขณะรู้จำเสียง:\n" + traceback.format_exc())

    # ---------------- start / stop ----------------
    def start(self, input_device, output_device, delay_seconds, mute_seconds,
              out_channels, language, pause_threshold=0.5, phrase_time_limit=4.0):
        if pyaudio is None or sr is None:
            raise RuntimeError("ยังไม่ได้ติดตั้ง PyAudio และ/หรือ SpeechRecognition")

        self.delay_seconds = max(delay_seconds, mute_seconds + BLOCK_SEC)
        self.mute_seconds = mute_seconds
        self.out_channels = max(1, int(out_channels))
        self.language = language
        self.pause_threshold = max(0.15, float(pause_threshold))
        self.phrase_time_limit = max(1.0, float(phrase_time_limit))
        self.delay_blocks = max(1, int(round(self.delay_seconds / BLOCK_SEC)))

        with self.buffer_lock:
            self.delay_buffer.clear()

        self.pa = pyaudio.PyAudio()
        try:
            self.in_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                input_device_index=input_device,
                frames_per_buffer=BLOCK_SIZE,
                stream_callback=self._input_callback,
            )
            self.out_stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.out_channels,
                rate=SAMPLE_RATE,
                output=True,
                output_device_index=output_device,
                frames_per_buffer=BLOCK_SIZE,
                stream_callback=self._output_callback,
            )
            self.in_stream.start_stream()
            self.out_stream.start_stream()
        except Exception:
            self._safe_close_streams()
            raise

        # ---- ตั้งค่า speech_recognition (เปิดไมค์ตัวเดียวกันอีก 1 stream แยกต่างหาก) ----
        # ปรับ pause_threshold / non_speaking_duration ให้สั้นลงเพื่อให้ตัดประโยค
        # เร็วขึ้น รองรับการพูดต่อเนื่อง และตรวจจับคำหยาบได้ไวขึ้น
        try:
            self.recognizer = sr.Recognizer()
            self.recognizer.dynamic_energy_threshold = True
            self.recognizer.pause_threshold = self.pause_threshold
            self.recognizer.non_speaking_duration = min(0.3, self.pause_threshold)
            self.mic_source = sr.Microphone(device_index=input_device, sample_rate=SAMPLE_RATE)
            with self.mic_source as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=1.0)
            self.stop_listening_fn = self.recognizer.listen_in_background(
                self.mic_source, self._on_phrase_recognized,
                phrase_time_limit=self.phrase_time_limit
            )
        except Exception:
            self._safe_close_streams()
            raise

        self.running = True

    def _safe_close_streams(self):
        for stream in (self.in_stream, self.out_stream):
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
        self.in_stream = None
        self.out_stream = None
        if self.pa is not None:
            try:
                self.pa.terminate()
            except Exception:
                pass
            self.pa = None

    def stop(self):
        self.running = False
        if self.stop_listening_fn is not None:
            try:
                self.stop_listening_fn(wait_for_stop=False)
            except Exception:
                pass
            self.stop_listening_fn = None
        self._safe_close_streams()


# ===========================================================================
# ส่วน UI (Tkinter)
# ===========================================================================
class CensorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("โปรแกรมเซ็นเซอร์คำไม่สุภาพแบบเรียลไทม์ (SpeechRecognition + PyAudio)")
        self.root.geometry("800x740")
        self.root.minsize(740, 680)

        self._loading = True  # กันไม่ให้ trace callback เซฟทับตอนกำลังโหลดค่า

        self.log_queue = queue.Queue()
        self.engine = CensorEngine(log_fn=lambda msg: self.log_queue.put(msg))

        self.settings = dict(DEFAULT_SETTINGS)

        self._build_ui()
        self._load_bad_words()
        self._load_settings()
        self._refresh_devices(select_saved=True)
        self._bind_autosave()

        self._loading = False

        self.root.after(100, self._poll_log)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if MISSING_LIBS:
            messagebox.showwarning(
                "ขาดไลบรารีที่จำเป็น",
                "กรุณาติดตั้งไลบรารีต่อไปนี้ก่อนใช้งาน:\n\n"
                + "pip install " + " ".join(MISSING_LIBS)
            )

        # ถ้าตั้งค่าไว้ให้เริ่มเซ็นเซอร์ทันทีที่เปิดโปรแกรม
        if self.settings.get("auto_start_engine") and not MISSING_LIBS:
            self.root.after(1200, self._start)

    # ---------------------------------------------------------------- UI ---
    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        # ---- ปุ่มเริ่ม/หยุด + สถานะ (อยู่บนสุด เห็นตลอด ไม่ว่าจะสลับแท็บไหน) ----
        control_frame = ttk.Frame(self.root)
        control_frame.pack(fill="x", **pad)

        self.start_btn = ttk.Button(control_frame, text="▶ เริ่มทำงาน", command=self._start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(control_frame, text="■ หยุด", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        self.status_var = tk.StringVar(value="สถานะ: หยุดทำงาน")
        ttk.Label(control_frame, textvariable=self.status_var, foreground="#0a5").pack(side="left", padx=16)

        # ---- แท็บหมวดหมู่ ----
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, **pad)

        tab_main = ttk.Frame(self.notebook)
        tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(tab_main, text="อุปกรณ์ & คำหยาบ")
        self.notebook.add(tab_settings, text="⚙ ตั้งค่า")

        # =========================== TAB 1: อุปกรณ์ & คำหยาบ ===========================
        dev_frame = ttk.LabelFrame(tab_main, text="อุปกรณ์เสียง")
        dev_frame.pack(fill="x", **pad)

        ttk.Label(dev_frame, text="ไมโครโฟน (Input):").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.input_combo = ttk.Combobox(dev_frame, state="readonly", width=55)
        self.input_combo.grid(row=0, column=1, padx=6, pady=4, sticky="we")

        ttk.Label(dev_frame, text="เอาต์พุต (Output / Virtual Cable):").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.output_combo = ttk.Combobox(dev_frame, state="readonly", width=55)
        self.output_combo.grid(row=1, column=1, padx=6, pady=4, sticky="we")

        ttk.Button(dev_frame, text="รีเฟรชอุปกรณ์", command=lambda: self._refresh_devices(select_saved=False)).grid(row=0, column=2, rowspan=2, padx=6)
        ttk.Label(dev_frame, text="(อุปกรณ์ที่เลือกจะถูกจดจำอัตโนมัติในครั้งถัดไป)", foreground="#888").grid(row=2, column=0, columnspan=3, sticky="w", padx=6)
        dev_frame.columnconfigure(1, weight=1)

        # ---- รายการคำไม่สุภาพ ----
        words_frame = ttk.LabelFrame(tab_main, text="รายการคำที่ต้องการเซ็นเซอร์ (บันทึกอัตโนมัติทุกครั้งที่แก้ไข)")
        words_frame.pack(fill="both", expand=True, **pad)

        list_container = ttk.Frame(words_frame)
        list_container.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

        self.words_listbox = tk.Listbox(list_container, height=10)
        self.words_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.words_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.words_listbox.config(yscrollcommand=scrollbar.set)

        btn_col = ttk.Frame(words_frame)
        btn_col.pack(side="left", fill="y", padx=6, pady=6)

        self.new_word_var = tk.StringVar()
        entry = ttk.Entry(btn_col, textvariable=self.new_word_var, width=20)
        entry.pack(pady=(0, 4))
        entry.bind("<Return>", lambda e: self._add_word())

        ttk.Button(btn_col, text="เพิ่มคำ", command=self._add_word).pack(fill="x", pady=2)
        ttk.Button(btn_col, text="ลบคำที่เลือก", command=self._remove_word).pack(fill="x", pady=2)
        ttk.Label(btn_col, text="(ทุกคำในรายการนี้\nจะถูกแบน/เซ็นเซอร์\nทุกครั้งที่พูด)",
                  foreground="#a55", justify="left").pack(pady=(12, 2))

        # =========================== TAB 2: ตั้งค่า ===========================
        rec_frame = ttk.LabelFrame(tab_settings, text="การรู้จำเสียง (Google Web Speech API)")
        rec_frame.pack(fill="x", **pad)

        ttk.Label(rec_frame, text="ภาษา:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.lang_combo = ttk.Combobox(rec_frame, state="readonly", width=25,
                                        values=[lbl for lbl, code in LANGUAGE_OPTIONS])
        self.lang_combo.current(0)
        self.lang_combo.grid(row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(rec_frame, text="(ต้องต่ออินเทอร์เน็ต)", foreground="#888").grid(row=0, column=2, sticky="w")

        cfg_frame = ttk.LabelFrame(tab_settings, text="ตั้งค่าการเซ็นเซอร์ / ความไวการตรวจจับ")
        cfg_frame.pack(fill="x", **pad)

        ttk.Label(cfg_frame, text="หน่วงเสียงทั้งหมด (วินาที):").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.delay_var = tk.DoubleVar(value=4.0)
        ttk.Spinbox(cfg_frame, from_=1.0, to=10.0, increment=0.5, textvariable=self.delay_var, width=8).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(cfg_frame, text="เซ็นเซอร์ย้อนหลังเมื่อเจอคำ (วินาที):").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        self.mute_var = tk.DoubleVar(value=2.5)
        ttk.Spinbox(cfg_frame, from_=0.5, to=8.0, increment=0.5, textvariable=self.mute_var, width=8).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(cfg_frame, text="ช่องสัญญาณเอาต์พุต:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.channels_var = tk.IntVar(value=2)
        ttk.Combobox(cfg_frame, state="readonly", width=6, textvariable=self.channels_var,
                     values=[1, 2]).grid(row=1, column=1, sticky="w", padx=6)

        ttk.Label(cfg_frame, text="ความไวตัดประโยค (วินาที, ยิ่งน้อยยิ่งต่อเนื่อง/ไว):").grid(row=1, column=2, sticky="w", padx=6, pady=4)
        self.pause_var = tk.DoubleVar(value=0.5)
        ttk.Spinbox(cfg_frame, from_=0.2, to=1.5, increment=0.1, textvariable=self.pause_var, width=8).grid(row=1, column=3, sticky="w", padx=6)

        ttk.Label(cfg_frame, text="ความยาวประโยคสูงสุด (วินาที):").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.phrase_var = tk.DoubleVar(value=4.0)
        ttk.Spinbox(cfg_frame, from_=2.0, to=10.0, increment=0.5, textvariable=self.phrase_var, width=8).grid(row=2, column=1, sticky="w", padx=6)

        note = ("หมายเหตุ: 'หน่วงเสียงทั้งหมด' ต้องมากพอครอบคลุมเวลาพูดจบประโยค + เวลาที่ระบบ\n"
                "ส่งเสียงไปประมวลผลออนไลน์แล้วได้ผลกลับมา ถ้าเซ็นเซอร์ไม่ทันให้เพิ่มค่านี้\n"
                "ส่วน 'ความไวตัดประโยค' ยิ่งตั้งน้อย ระบบจะตัดคำ/ประโยคให้ไปตรวจสอบเร็วขึ้น\n"
                "ทำให้พูดต่อเนื่องได้ลื่นและตรวจจับคำหยาบได้ไวขึ้น แต่ถ้าน้อยเกินไปอาจตัดคำผิดจังหวะ")
        ttk.Label(cfg_frame, text=note, foreground="#a55", justify="left").grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(4, 4))

        # ---- ไฟล์เสียงเซ็นเซอร์ ----
        sound_frame = ttk.LabelFrame(tab_settings, text="เสียงที่ใช้เซ็นเซอร์ (ค่าเริ่มต้น = เสียงปี๊บ)")
        sound_frame.pack(fill="x", **pad)
        self.sound_path_var = tk.StringVar(value="(ใช้เสียงปี๊บมาตรฐาน)")
        ttk.Label(sound_frame, textvariable=self.sound_path_var, foreground="#444").pack(side="left", padx=6, fill="x", expand=True)
        ttk.Button(sound_frame, text="ทดสอบเล่นเสียง", command=self._preview_sound).pack(side="right", padx=6, pady=6)
        ttk.Button(sound_frame, text="เลือกไฟล์เสียง...", command=self._choose_sound_file).pack(side="right", padx=6, pady=6)
        ttk.Button(sound_frame, text="ใช้เสียงปี๊บ default", command=self._use_default_beep).pack(side="right", padx=6, pady=6)

        # ---- เริ่มอัตโนมัติ ----
        startup_frame = ttk.LabelFrame(tab_settings, text="การเริ่มทำงานอัตโนมัติ")
        startup_frame.pack(fill="x", **pad)

        self.auto_win_var = tk.BooleanVar(value=False)
        win_chk = ttk.Checkbutton(
            startup_frame,
            text="เปิดโปรแกรมนี้อัตโนมัติทุกครั้งที่เปิดเครื่อง (Windows Startup)",
            variable=self.auto_win_var,
            command=self._toggle_windows_startup,
        )
        win_chk.pack(anchor="w", padx=6, pady=(6, 2))
        if not IS_WINDOWS:
            win_chk.config(state="disabled")
            ttk.Label(startup_frame, text="(รองรับเฉพาะ Windows)", foreground="#888").pack(anchor="w", padx=26)

        self.auto_engine_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            startup_frame,
            text="เริ่มเซ็นเซอร์เสียงทันทีที่เปิดโปรแกรมนี้ขึ้นมา (ไม่ต้องกด ▶ เริ่มทำงาน เอง)",
            variable=self.auto_engine_var,
            command=self._save_settings,
        ).pack(anchor="w", padx=6, pady=(2, 6))

        # ---- log ----
        log_frame = ttk.LabelFrame(tab_settings, text="บันทึกการทำงาน")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_box = scrolledtext.ScrolledText(log_frame, height=8, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=6, pady=6)

    # ------------------------------------------------------------ helpers --
    def log(self, msg):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _poll_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    # ---- บันทึกอัตโนมัติทุกครั้งที่มีการเปลี่ยนค่าใด ๆ ----
    def _bind_autosave(self):
        self.input_combo.bind("<<ComboboxSelected>>", lambda e: self._save_settings())
        self.output_combo.bind("<<ComboboxSelected>>", lambda e: self._save_settings())
        self.lang_combo.bind("<<ComboboxSelected>>", lambda e: self._save_settings())
        for var in (self.delay_var, self.mute_var, self.channels_var,
                    self.pause_var, self.phrase_var):
            var.trace_add("write", lambda *a: self._save_settings())

    def _refresh_devices(self, select_saved=False):
        if pyaudio is None:
            self.log("ไม่พบไลบรารี PyAudio จึงแสดงรายชื่ออุปกรณ์ไม่ได้")
            return
        try:
            pa = pyaudio.PyAudio()
            count = pa.get_device_count()
            in_labels, out_labels = [], []
            for idx in range(count):
                info = pa.get_device_info_by_index(idx)
                name = info.get("name", f"device {idx}")
                if info.get("maxInputChannels", 0) > 0:
                    in_labels.append(f"[{idx}] {name}")
                if info.get("maxOutputChannels", 0) > 0:
                    out_labels.append(f"[{idx}] {name}")
            pa.terminate()
        except Exception as e:
            self.log(f"ดึงรายชื่ออุปกรณ์เสียงไม่สำเร็จ: {e}")
            return

        self.input_combo["values"] = in_labels
        self.output_combo["values"] = out_labels

        picked_in = picked_out = False
        if select_saved:
            saved_in_idx = self.settings.get("input_device_index")
            saved_out_idx = self.settings.get("output_device_index")
            saved_in_name = self.settings.get("input_device_name", "")
            saved_out_name = self.settings.get("output_device_name", "")
            if saved_in_idx is not None:
                for lbl in in_labels:
                    if lbl.startswith(f"[{saved_in_idx}]") or (saved_in_name and saved_in_name in lbl):
                        self.input_combo.set(lbl)
                        picked_in = True
                        break
            if saved_out_idx is not None:
                for lbl in out_labels:
                    if lbl.startswith(f"[{saved_out_idx}]") or (saved_out_name and saved_out_name in lbl):
                        self.output_combo.set(lbl)
                        picked_out = True
                        break

        if in_labels and not picked_in and not self.input_combo.get():
            self.input_combo.current(0)
        if out_labels and not picked_out and not self.output_combo.get():
            self.output_combo.current(0)
        self.log("รีเฟรชรายชื่ออุปกรณ์เสียงแล้ว")

    def _choose_sound_file(self):
        path = filedialog.askopenfilename(
            title="เลือกไฟล์เสียงสำหรับใช้เซ็นเซอร์",
            filetypes=[("Audio files", "*.wav *.flac *.ogg"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.engine.load_censor_file(path)
            self.sound_path_var.set(path)
            self.log(f"ใช้ไฟล์เสียงเซ็นเซอร์: {path}")
        except Exception as e:
            messagebox.showerror("โหลดไฟล์เสียงไม่สำเร็จ", str(e))

    def _use_default_beep(self):
        self.engine.censor_wave = self.engine._generate_beep()
        self.engine.censor_file_path = None
        self.sound_path_var.set("(ใช้เสียงปี๊บมาตรฐาน)")
        self.log("เปลี่ยนกลับไปใช้เสียงปี๊บมาตรฐานแล้ว")

    def _preview_sound(self):
        if pyaudio is None:
            messagebox.showerror("ผิดพลาด", "ยังไม่ได้ติดตั้ง PyAudio")
            return
        try:
            self.engine.preview_censor_sound()
        except Exception as e:
            messagebox.showerror("เล่นเสียงไม่ได้", str(e))

    # ---- คำไม่สุภาพ (บันทึกอัตโนมัติทุกครั้งที่เพิ่ม/ลบ) ----
    def _load_bad_words(self):
        words = []
        if os.path.exists(WORDS_FILE):
            try:
                with open(WORDS_FILE, "r", encoding="utf-8") as f:
                    words = json.load(f)
            except Exception:
                words = []
        for w in words:
            self.words_listbox.insert("end", w)
        self.engine.set_bad_words(words)

    def _save_bad_words(self):
        words = list(self.words_listbox.get(0, "end"))
        try:
            with open(WORDS_FILE, "w", encoding="utf-8") as f:
                json.dump(words, f, ensure_ascii=False, indent=2)
            self.engine.set_bad_words(words)
        except Exception as e:
            messagebox.showerror("บันทึกไม่สำเร็จ", str(e))

    def _add_word(self):
        w = self.new_word_var.get().strip()
        if not w:
            return
        current = list(self.words_listbox.get(0, "end"))
        if w in current:
            self.new_word_var.set("")
            return
        self.words_listbox.insert("end", w)
        self.new_word_var.set("")
        self._save_bad_words()
        self.log(f"เพิ่มคำหยาบ '{w}' และบันทึกอัตโนมัติแล้ว")

    def _remove_word(self):
        sel = self.words_listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            self.words_listbox.delete(i)
        self._save_bad_words()
        self.log("ลบคำที่เลือกและบันทึกอัตโนมัติแล้ว")

    # ---- เริ่มโปรแกรมอัตโนมัติเมื่อเปิดเครื่อง ----
    def _toggle_windows_startup(self):
        enable = self.auto_win_var.get()
        try:
            set_windows_startup(enable)
            self.log("เปิดใช้งานเริ่มโปรแกรมอัตโนมัติตอนเปิดเครื่องแล้ว" if enable
                      else "ปิดการเริ่มโปรแกรมอัตโนมัติตอนเปิดเครื่องแล้ว")
        except Exception as e:
            self.auto_win_var.set(not enable)
            messagebox.showerror("ตั้งค่าไม่สำเร็จ", str(e))
            return
        self._save_settings()

    # ---- settings (โหลด / บันทึกอัตโนมัติ) ----
    def _load_settings(self):
        s = dict(DEFAULT_SETTINGS)
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                s.update(loaded)
            except Exception:
                pass
        self.settings = s

        self.delay_var.set(s.get("delay_seconds", 4.0))
        self.mute_var.set(s.get("mute_seconds", 2.5))
        self.channels_var.set(s.get("out_channels", 2))
        self.pause_var.set(s.get("pause_threshold", 0.5))
        self.phrase_var.set(s.get("phrase_time_limit", 4.0))

        lang_code = s.get("language", "th-TH")
        for i, (lbl, code) in enumerate(LANGUAGE_OPTIONS):
            if code == lang_code:
                self.lang_combo.current(i)
                break

        self.auto_engine_var.set(bool(s.get("auto_start_engine", False)))
        # สถานะ startup จริงให้อ่านจาก registry เสมอ (เผื่อถูกแก้จากที่อื่น)
        self.auto_win_var.set(is_windows_startup_enabled())

    def _save_settings(self):
        if getattr(self, "_loading", False):
            return
        try:
            lang_idx = self.lang_combo.current()
            lang_code = LANGUAGE_OPTIONS[lang_idx][1] if lang_idx >= 0 else "th-TH"

            in_sel = self.input_combo.get()
            out_sel = self.output_combo.get()
            in_idx = in_name = None
            out_idx = out_name = None
            if in_sel and "]" in in_sel:
                in_idx = int(in_sel.split("]")[0].strip("["))
                in_name = in_sel.split("]", 1)[1].strip()
            if out_sel and "]" in out_sel:
                out_idx = int(out_sel.split("]")[0].strip("["))
                out_name = out_sel.split("]", 1)[1].strip()

            self.settings = {
                "delay_seconds": float(self.delay_var.get()),
                "mute_seconds": float(self.mute_var.get()),
                "out_channels": int(self.channels_var.get()),
                "language": lang_code,
                "pause_threshold": float(self.pause_var.get()),
                "phrase_time_limit": float(self.phrase_var.get()),
                "input_device_index": in_idx,
                "input_device_name": in_name or "",
                "output_device_index": out_idx,
                "output_device_name": out_name or "",
                "auto_start_windows": bool(self.auto_win_var.get()),
                "auto_start_engine": bool(self.auto_engine_var.get()),
            }
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- start / stop ----
    def _start(self):
        if MISSING_LIBS:
            messagebox.showerror("ขาดไลบรารี", "กรุณาติดตั้ง: pip install " + " ".join(MISSING_LIBS))
            return
        in_sel = self.input_combo.get()
        out_sel = self.output_combo.get()
        if not in_sel or not out_sel:
            messagebox.showerror("ผิดพลาด", "กรุณาเลือกอุปกรณ์ไมโครโฟนและเอาต์พุต")
            return

        try:
            in_idx = int(in_sel.split("]")[0].strip("["))
            out_idx = int(out_sel.split("]")[0].strip("["))
            lang_idx = self.lang_combo.current()
            lang_code = LANGUAGE_OPTIONS[lang_idx][1] if lang_idx >= 0 else "th-TH"

            self.engine.set_bad_words(list(self.words_listbox.get(0, "end")))
            self.engine.start(
                input_device=in_idx,
                output_device=out_idx,
                delay_seconds=float(self.delay_var.get()),
                mute_seconds=float(self.mute_var.get()),
                out_channels=int(self.channels_var.get()),
                language=lang_code,
                pause_threshold=float(self.pause_var.get()),
                phrase_time_limit=float(self.phrase_var.get()),
            )
        except Exception as e:
            messagebox.showerror("เริ่มทำงานไม่สำเร็จ", f"{e}")
            self.log("เริ่มทำงานไม่สำเร็จ:\n" + traceback.format_exc())
            return

        self._save_settings()
        self.status_var.set("สถานะ: กำลังทำงาน 🔴")
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log("เริ่มการเซ็นเซอร์เสียงแบบเรียลไทม์แล้ว (กำลังปรับเทียบเสียงรบกวนรอบข้าง...)")

    def _stop(self):
        self.engine.stop()
        self.status_var.set("สถานะ: หยุดทำงาน")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.log("หยุดการทำงานแล้ว")

    def _on_close(self):
        try:
            self.engine.stop()
        except Exception:
            pass
        self._save_settings()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass
    app = CensorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
