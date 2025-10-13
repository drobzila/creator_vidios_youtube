#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📽️ Quran Video Maker — Final Integrated Version (v3)
by Mohamed — Auto-run via GitHub Actions

الوظائف:
1. يجلب الكرومات (فيديوهات أقل من 180 ثانية) من قناة تلغرام.
2. يجلب الخلفيات من مجلد Google Drive.
3. يزيل الخلفية السوداء من الكروما ويضعها فوق الخلفية.
4. يحفظ الفيديو النهائي ويرفعه إلى مجلد Drive آخر.
5. يسجل كل العمليات في output_logs/history.log.
"""

import os, io, sys, base64, sqlite3, asyncio, random, datetime, tempfile, subprocess
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# -----------------------------
# 🔧 الإعدادات العامة
# -----------------------------
api_id = 27874350
api_hash = "a8cca90ec7d1023b8118163822f187c0"
channel_username = "quranbng"

CLIENT_ID = "553805965519-1gvas0tmcl86v76k7m9bhkmc7m76657s.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REFRESH_TOKEN = "1//09SLS4A1oZYsJCgYIARAAGAkSNwF-L9IrQJneNmOVOAjihJWVMGFL2gYlLAdg0Y_0SZg4bQPjbRR-qkDKYvbSS4weE7zrPh8w4_E"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive"]

DRIVE_BG_FOLDER_ID = "1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C"     # الخلفيات
DRIVE_OUTPUT_FOLDER_ID = "1lLKbFPovufWeEkwpCgI3cM-Je-Uee9el"  # الناتج

# المسارات
BASE_DIR = Path.cwd()
CHROMAS_DIR = BASE_DIR / "chromas"
BACKGROUND_DIR = BASE_DIR / "background_videos"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "output_logs"
DB_PATH = BASE_DIR / "processed.db"
for d in (CHROMAS_DIR, BACKGROUND_DIR, OUTPUTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# إعدادات ffmpeg
FFMPEG = "ffmpeg"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
PRESET = "veryfast"
CRF = "23"
MAX_CHROMA_SEC = 180  # تم رفع الحد
MAX_FILE_SIZE_MB = 10  # أقصى حجم للفيديو من تلغرام

# -----------------------------
# ⚙️ إدارة الجلسة
# -----------------------------
def ensure_telegram_session():
    session_file = BASE_DIR / "session.session"
    if session_file.exists():
        print("✅ Using existing session.session file.")
        return str(session_file)

    b64_file = BASE_DIR / "session.b64"
    if b64_file.exists():
        print("📦 Decoding session.b64 file...")
        data = base64.b64decode(b64_file.read_bytes())
        session_file.write_bytes(data)
        os.chmod(session_file, 0o600)
        return str(session_file)

    env_b64 = os.environ.get("TELEGRAM_SESSION_B64")
    if env_b64:
        print("📦 Decoding TELEGRAM_SESSION_B64 from env...")
        data = base64.b64decode(env_b64)
        session_file.write_bytes(data)
        os.chmod(session_file, 0o600)
        return str(session_file)

    print("⚠️ No session found — Telethon will try to log in interactively.")
    return "session.session"

# -----------------------------
# 🧱 قاعدة البيانات
# -----------------------------
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

# -----------------------------
# ☁️ Google Drive
# -----------------------------
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
    files, token = [], None
    while True:
        res = service.files().list(
            q=q, spaces='drive',
            fields='nextPageToken, files(id,name)',
            pageToken=token
        ).execute()
        files += res.get('files', [])
        token = res.get('nextPageToken')
        if not token:
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
# 🤖 تحميل الكرومات من تلغرام
# -----------------------------
async def fetch_chromas(api_id, api_hash, channel, session_path):
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()
    conn = init_db()
    c = conn.cursor()
    new_files = []

    print("📡 Searching for short videos...")
    async for msg in client.iter_messages(channel, limit=500):
        video_file, duration, file_size = None, None, 0

        if msg.video:
            video_file = msg.video
            duration = getattr(msg.video, "duration", 0)
            file_size = getattr(msg.video, "size", 0)
        elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/"):
            video_file = msg.document
            for attr in video_file.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    duration = getattr(attr, "duration", 0)
            file_size = getattr(msg.file, "size", 0)

        if not video_file or not duration:
            continue
        if duration > MAX_CHROMA_SEC:
            continue
        if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
            continue
        if c.execute("SELECT 1 FROM processed WHERE msg_id=?", (msg.id,)).fetchone():
            continue

        dest = CHROMAS_DIR / f"{msg.id}.mp4"
        print(f"⬇️ Downloading chroma {msg.id} ({round(duration)}s)...")
        await msg.download_media(file=str(dest))
        c.execute("INSERT OR REPLACE INTO processed VALUES (?,?,?)",
                  (msg.id, dest.name, datetime.datetime.utcnow().isoformat()))
        conn.commit()
        new_files.append(dest)

    await client.disconnect()
    return new_files

# -----------------------------
# 🎬 الدمج باستخدام ffmpeg
# -----------------------------
def get_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries",
           "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except:
        return 0.0

def merge(chroma, background, output):
    dur = get_duration(chroma)
    print(f"🎞 Merging {chroma.name} with {background.name} ({dur:.1f}s)...")

    tmp_bg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run([FFMPEG, "-y", "-i", str(background), "-t", str(dur),
                    "-c", "copy", tmp_bg], check=True)

    cmd = [
        FFMPEG, "-y",
        "-i", tmp_bg, "-i", str(chroma),
        "-filter_complex", "[1:v]colorkey=0x000000:0.3:0.2[ck];[0:v][ck]overlay[outv]",
        "-map", "[outv]", "-map", "1:a?",
        "-c:v", VIDEO_CODEC, "-preset", PRESET, "-crf", CRF,
        "-c:a", AUDIO_CODEC, "-b:a", "128k",
        str(output)
    ]
    subprocess.run(cmd, check=True)
    os.remove(tmp_bg)

# -----------------------------
# 🚀 الدالة الرئيسية
# -----------------------------
async def main():
    session_path = ensure_telegram_session()
    print("Session ready:", session_path)

    conn = init_db()
    drive = get_drive_service()

    print("📥 Fetching chromas from Telegram...")
    chromas = await fetch_chromas(api_id, api_hash, channel_username, session_path)
    if not chromas:
        print("⚠️ No new chromas found.")
        (LOGS_DIR / "history.log").touch(exist_ok=True)
        return

    print("☁️ Fetching backgrounds from Google Drive...")
    bg_files = list_drive_files(drive, DRIVE_BG_FOLDER_ID)
    if not bg_files:
        print("❌ No backgrounds found.")
        return

    for bg in bg_files:
        dest = BACKGROUND_DIR / bg["name"]
        if not dest.exists():
            print(f"⬇️ Downloading background {bg['name']}...")
            download_file(drive, bg["id"], str(dest))

    bg_list = list(BACKGROUND_DIR.glob("*"))
    if not bg_list:
        print("❌ No local backgrounds available.")
        return

    for chroma in chromas:
        bg = random.choice(bg_list)
        out_name = f"final_{chroma.stem}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        out_path = OUTPUTS_DIR / out_name

        try:
            merge(chroma, bg, out_path)
            print(f"✅ Created {out_name}")
            file_id = upload_file(drive, out_path, DRIVE_OUTPUT_FOLDER_ID)
            print(f"☁️ Uploaded to Drive (ID: {file_id})")
            with open(LOGS_DIR / "history.log", "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.utcnow().isoformat()} | {chroma.name} -> {out_name} | {file_id}\n")
        except Exception as e:
            print("❌ Merge or upload failed:", e)

    conn.close()
    (LOGS_DIR / "history.log").touch(exist_ok=True)
    print("🏁 Done.")

# -----------------------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Script failed:", e)
        sys.exit(1)
