#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quran Video Maker — Final
- يختار 5 كرومات يوميًا (≤ 60s) من قناة Telegram (quranbng)
- يجعل الناتج شورت عمودي 1080x1920
- يستخدم خلفيات من Google Drive (المجلد كما هو)
- لا يعيد معالجة كرومات سبق تسجيلها (SQLite)
- يعالج إزالة الخلفية السوداء بالـ colorkey ثم يرفع الناتج إلى Drive
"""

import os
import io
import sys
import asyncio
import random
import datetime
import sqlite3
import subprocess
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# -----------------------------
# إعدادات - عدّل هنا فقط عند الحاجة
# -----------------------------
api_id = 27874350
api_hash = "a8cca90ec7d1023b8118163822f187c0"
channel_username = "quranbng"

CLIENT_ID = "553805965519-1gvas0tmcl86v76k7m9bhkmc7m76657s.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REFRESH_TOKEN = "1//09SLS4A1oZYsJCgYIARAAGAkSNwF-L9IrQJneNmOVOAjihJWVMGFL2gYlLAdg0Y_0SZg4bQPjbRR-qkDKYvbSS4weE7zrPh8w4_E"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive"]

DRIVE_BG_FOLDER_ID = "1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C"     # خلفيات (لا تغيّر)
DRIVE_OUTPUT_FOLDER_ID = "1lLKbFPovufWeEkwpCgI3cM-Je-Uee9el"  # ناتج (لا تغيّر)

BASE_DIR = Path.cwd()
CHROMAS_DIR = BASE_DIR / "chromas"
BACKGROUND_DIR = BASE_DIR / "background_videos"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "output_logs"
DB_PATH = BASE_DIR / "processed.db"

for d in (CHROMAS_DIR, BACKGROUND_DIR, OUTPUTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ffmpeg settings
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
TARGET_W, TARGET_H = 1080, 1920   # شورت عمودي
DAILY_LIMIT = 5
MAX_CHROMA_SEC = 60

# عناوين عشوائية
video_titles = [
    "استمتع بسكينة القرآن", "عِش راحة القرآن", "لحظة مع كلام الله", "جمال التلاوة", "نور قلبك بالقرآن",
    "همسات قرآنية", "ترتيل يشرح الصدر", "أنفاس قرآنية", "رحلة مع القرآن", "معاني تطمئن القلب",
    "روعة الصوت القرآني", "طمأنينة من السماء", "قرآن يهز المشاعر", "موسيقى السماء", "صوت الملائكة",
    "صفاء النفس بالقرآن", "ترانيم الرحمة", "آيات تلين القلوب", "نور بين السطور", "سكون القلب",
    "قرآن الشفاء", "خُشوع لا يُوصف", "صوت يحيي الأرواح", "صدى الجنة", "بصوت من الجنة",
    "عيش القرآن بجوارحك", "هدوء القرآن", "نفحات قرآنية", "إيمان متجدد", "تلاوة تذيب القلوب",
    "صوت يهز الوجد", "لحظة روحانية", "القرآن كما لم تسمعه من قبل", "سافر مع القرآن", "تأمل آية",
    "حديث الله إليك", "بوح السماء", "قرآن ينير الدرب", "صوت يرقى بالروح", "لحن الرحمة",
    "ركن الهدوء", "أنفاس السكينة", "نبض التلاوة", "فيض القرآن", "القرآن حياة", "ذِكر طيب",
    "أصوات من الجنة", "نور التلاوة", "رحمة القرآن", "مرفأ الطمأنينة", "سُطور نورانية",
    "طيف من الجنة", "السكينة في التلاوة", "بوح من السماء", "صفحة من نور", "عبق القرآن",
    "صوت الإيمان", "تلاوة تهدئ القلب", "آية تغير الحياة", "أمان الروح", "صوت يلامس القلب",
    "من أعماق الإيمان", "كلام الله يصل الأعماق", "هُدى ونور", "ارتقاء بالقرآن", "صوت يطهر القلب",
    "لحظة مع الإيمان", "في حضرة القرآن", "أنغام السماء", "آيات تلامس الأرواح", "خشوع لا يُضاهى",
    "جمال من الجنة", "صوت ينقلك لعالم آخر", "نورك في القرآن", "شوق للآيات", "بوح الإيمان",
    "نقاء التلاوة", "عذوبة القرآن", "صوت يحملك للسكينة", "مرفأ الإيمان", "القرآن طمأنينة",
    "هُدى الرحمن", "بوح الروح", "دقائق مع الله", "لحظات إيمانية", "ترتيل من القلب", "نور الروح",
    "ترانيم إيمانية", "صوت هادئ ونقي", "عبادة بالصوت", "أنفاس الإيمان", "همس التلاوة",
    "لحظة نقاء", "فيض نوراني", "آيات تتغلغل في القلب", "ترتيل مطمئن", "صوت مريح للنفس",
    "رحلة سماوية", "بوح الآيات", "دعاء يتلى", "القرآن رفيقك", "صوت يتسلل إلى روحك"
]

# -----------------------------
# وظائف مساعدة
# -----------------------------
def check_tools():
    """تأكد من توفر ffmpeg و ffprobe"""
    def exists(cmd):
        try:
            subprocess.run([cmd, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except FileNotFoundError:
            return False
    ok_ffmpeg = exists(FFMPEG)
    ok_ffprobe = exists(FFPROBE)
    if not ok_ffmpeg or not ok_ffprobe:
        print("❌ يتطلب وجود ffmpeg و ffprobe في PATH.")
        if not ok_ffmpeg:
            print("  - ffmpeg غير موجود")
        if not ok_ffprobe:
            print("  - ffprobe غير موجود")
        sys.exit(1)

def ensure_telegram_session():
    session_file = BASE_DIR / "session.session"
    if session_file.exists():
        return str(session_file)
    b64_file = BASE_DIR / "session.b64"
    if b64_file.exists():
        data = b64_file.read_bytes()
        import base64
        session_file.write_bytes(base64.b64decode(data))
        os.chmod(session_file, 0o600)
        return str(session_file)
    env_b64 = os.environ.get("TELEGRAM_SESSION_B64")
    if env_b64:
        import base64
        session_file.write_bytes(base64.b64decode(env_b64))
        os.chmod(session_file, 0o600)
        return str(session_file)
    return str(session_file)  # Telethon سيطلب تسجيل الدخول تفاعليًا إن لزم

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS processed(
        msg_id INTEGER PRIMARY KEY,
        filename TEXT,
        processed_at TEXT
    )""")
    conn.commit()
    return conn

def get_drive_service():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES,
    )
    creds.refresh(Request())
    return build('drive', 'v3', credentials=creds, cache_discovery=False)

def list_drive_files(service, folder_id):
    q = f"'{folder_id}' in parents and trashed=false"
    files = []
    page_token = None
    while True:
        res = service.files().list(q=q, spaces='drive', fields='nextPageToken, files(id,name)', pageToken=page_token).execute()
        files += res.get('files', [])
        page_token = res.get('nextPageToken')
        if not page_token:
            break
    return files

def download_file(service, file_id, dest):
    req = service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest, 'wb')
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.close()

def upload_file(service, path, folder_id):
    meta = {'name': path.name, 'parents': [folder_id]}
    media = MediaFileUpload(str(path), resumable=True)
    file = service.files().create(body=meta, media_body=media, fields='id').execute()
    return file['id']

# -----------------------------
# تلغرام: جلب كرومات جديدة (يومياً 5)
# -----------------------------
async def fetch_chromas(api_id, api_hash, channel, session_path, db_conn):
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()
    c = db_conn.cursor()
    new_files = []

    print(f"📡 Searching for up to {DAILY_LIMIT} new chromas (≤ {MAX_CHROMA_SEC}s)...")
    async for msg in client.iter_messages(channel, reverse=False):
        # تأكد أن الرسالة تحتوي فيديو أو وثيقة فيديو
        duration = None
        if msg.video:
            for attr in getattr(msg.video, "attributes", []):
                duration = getattr(attr, "duration", None) or duration
        elif msg.document and getattr(msg.document, "mime_type", "").startswith("video/"):
            for attr in getattr(msg.document, "attributes", []):
                duration = getattr(attr, "duration", None) or duration

        if duration is None:
            continue
        # شرط الطول
        if duration > MAX_CHROMA_SEC:
            continue
        # هل عولجت سابقًا؟
        if c.execute("SELECT 1 FROM processed WHERE msg_id=?", (msg.id,)).fetchone():
            continue

        dest = CHROMAS_DIR / f"{msg.id}.mp4"
        print(f"⬇️ Downloading short chroma {msg.id} ({int(duration)}s)...")
        # حاول 3 مرات
        for attempt in range(3):
            try:
                await msg.download_media(file=str(dest))
                break
            except Exception as e:
                print(f" ⚠️ Attempt {attempt+1} failed: {e}")
                await asyncio.sleep(5)
        if not dest.exists():
            print(" ❌ failed to download, skipping.")
            continue

        # سجل في DB فور التحميل - حتى لا يعاد لاحقاً
        c.execute("INSERT OR REPLACE INTO processed (msg_id, filename, processed_at) VALUES (?,?,?)",
                  (msg.id, dest.name, datetime.datetime.utcnow().isoformat()))
        db_conn.commit()

        new_files.append(dest)
        if len(new_files) >= DAILY_LIMIT:
            print("✅ Daily limit reached.")
            break
    await client.disconnect()
    return new_files

# -----------------------------
# ffmpeg: تحضير ودمج (مقسّم)
# -----------------------------
def get_duration_seconds(path):
    try:
        out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                             capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return None

def produce_final(chroma_path: Path, bg_path: Path, out_path: Path, title: str):
    """
    1) نقص/نكرر الخلفية لتطابق مدة الكروما
    2) نحول الخلفية لمقاس الشورت 1080x1920 (scale+pad) وندمج الكروما فوقها بإزالة اللون الأسود (colorkey)
    3) نحفظ الصوت من الكروما إن وُجد
    """
    chroma_dur = get_duration_seconds(chroma_path)
    if chroma_dur is None:
        raise RuntimeError("Could not probe chroma duration")

    # مؤقت لنسخ الخلفية بطول الكروما
    tmp_bg = out_path.with_suffix(".bg_tmp.mp4")
    # 1- تحويل الخلفية لتناسب الشورت وإطالتها/قصها لتطابق مدة الكروما
    # force_original_aspect_ratio=decrease ثم pad إلى 1080x1920 بمركزية
    cmd_bg = [
        FFMPEG, "-y", "-i", str(bg_path),
        "-t", str(chroma_dur),
        "-vf", f"scale=w={TARGET_W}:h={TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(tmp_bg)
    ]
    subprocess.run(cmd_bg, check=True)

    # 2- نستخدم filter_complex:
    # - نُقحم الكروما ثم نُطبق scale لتصغيرها إن لزم ثم colorkey ثم overlay متمركزًا
    # - نختار صوت الكروما (إن وُجد)، وإلا نترك صوت الخلفية
    out_tmp = out_path.with_suffix(".tmp.mp4")
    filter_chroma_scale = f"scale=w={TARGET_W}:h={TARGET_H}:force_original_aspect_ratio=decrease"
    # تحديد موضع overlay ليتوسط الخلفية
    overlay_pos = "(W-w)/2:(H-h)/2"
    cmd_merge = [
        FFMPEG, "-y",
        "-i", str(tmp_bg),
        "-i", str(chroma_path),
        "-filter_complex",
        f"[1:v]{filter_chroma_scale},colorkey=0x000000:0.3:0.15[ck];[0:v][ck]overlay={overlay_pos}:format=yuv420",
        "-map", "0:v", "-map", "1:a?",  # استخدم صوت الكروما إن وُجد
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        str(out_tmp)
    ]
    subprocess.run(cmd_merge, check=True)

    # نظف الوسائط المؤقتة
    if tmp_bg.exists():
        tmp_bg.unlink()

    # أخيراً: إذا الملف الناتج أكبر من 50MB يمكنك ضغطه لاحقًا - هنا نترك إعدادات CRF أعلاه
    os.replace(str(out_tmp), str(out_path))

# -----------------------------
# main()
# -----------------------------
async def main():
    check_tools()
    session_path = ensure_telegram_session()
    print("Session ready:", session_path)

    conn = init_db()
    drive = None
    try:
        drive = get_drive_service()
    except Exception as e:
        print("❌ Failed to init Drive service:", e)
        drive = None

    print("📥 Fetching new short chromas from Telegram...")
    chromas = await fetch_chromas(api_id, api_hash, channel_username, session_path, conn)
    if not chromas:
        print("⚠️ No new chromas found.")
    else:
        # تنزيل الخلفيات من Drive
        if drive:
            print("☁️ Syncing backgrounds from Drive folder...")
            try:
                files = list_drive_files(drive, DRIVE_BG_FOLDER_ID)
                for f in files:
                    dest = BACKGROUND_DIR / f["name"]
                    if not dest.exists():
                        print("⬇️ Downloading background", f["name"])
                        download_file(drive, f["id"], str(dest))
            except Exception as e:
                print("❌ Error syncing backgrounds:", e)

        # احصل قائمة خلفيات محلية
        bg_list = list(BACKGROUND_DIR.glob("*"))
        if not bg_list:
            print("❌ No local backgrounds available — تأكد من رفع الخلفيات إلى Drive أو وضع ملفات في background_videos/")
        else:
            print(f"🎬 Creating finals for {len(chromas)} chromas...")
            for chroma in chromas:
                # عنوان عشوائي
                title = random.choice(video_titles)
                safe_name = "".join(c for c in title if c.isalnum() or c in " _-").strip()
                out_name = f"final_{chroma.stem}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}.mp4"
                out_path = OUTPUTS_DIR / out_name

                bg = random.choice(bg_list)

                try:
                    produce_final(chroma, bg, out_path, title)
                    print("✅ Created", out_name)
                    # رفع إلى Drive إن أمكن
                    if drive:
                        try:
                            fid = upload_file(drive, out_path, DRIVE_OUTPUT_FOLDER_ID)
                            print("☁️ Uploaded:", fid)
                            with open(LOGS_DIR / "history.log", "a", encoding="utf-8") as f:
                                f.write(f"{datetime.datetime.utcnow().isoformat()} | {chroma.name} -> {out_name} | {fid}\n")
                        except Exception as e:
                            print("❌ Upload failed:", e)
                            with open(LOGS_DIR / "history.log", "a", encoding="utf-8") as f:
                                f.write(f"{datetime.datetime.utcnow().isoformat()} | {chroma.name} -> {out_name} | UPLOAD_FAILED: {e}\n")
                    else:
                        with open(LOGS_DIR / "history.log", "a", encoding="utf-8") as f:
                            f.write(f"{datetime.datetime.utcnow().isoformat()} | {chroma.name} -> {out_name} | local_only\n")
                except Exception as e:
                    print("❌ Error with", chroma.name, ":", e)
                    with open(LOGS_DIR / "history.log", "a", encoding="utf-8") as f:
                        f.write(f"{datetime.datetime.utcnow().isoformat()} | {chroma.name} -> ERROR: {e}\n")

    conn.close()
    print("🏁 Done.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Script failed:", e)
        sys.exit(1)
