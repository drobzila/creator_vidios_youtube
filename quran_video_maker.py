#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📽️ Quran Video Maker — Auto short chromas downloader (≤ 60s)
By Mohamed — Runs daily via GitHub Actions
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
# 🔧 إعدادات عامة
# -----------------------------
api_id = 27874350
api_hash = "a8cca90ec7d1023b8118163822f187c0"
channel_username = "quranbng"

CLIENT_ID = "553805965519-1gvas0tmcl86v76k7m9bhkmc7m76657s.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REFRESH_TOKEN = "1//09SLS4A1oZYsJCgYIARAAGAkSNwF-L9IrQJneNmOVOAjihJWVMGFL2gYlLAdg0Y_0SZg4bQPjbRR-qkDKYvbSS4weE7zrPh8w4_E"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive"]

DRIVE_BG_FOLDER_ID = "1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C"
DRIVE_OUTPUT_FOLDER_ID = "1lLKbFPovufWeEkwpCgI3cM-Je-Uee9el"

BASE_DIR = Path.cwd()
CHROMAS_DIR = BASE_DIR / "chromas"
BACKGROUND_DIR = BASE_DIR / "background_videos"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "output_logs"
DB_PATH = BASE_DIR / "processed.db"
for d in (CHROMAS_DIR, BACKGROUND_DIR, OUTPUTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# -----------------------------
# 🧠 دالة الحصول على مدة الفيديو
# -----------------------------
def get_duration(video_path: str) -> float:
    """إرجاع مدة الفيديو بالثواني باستخدام FFmpeg"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        return float(result.stdout.strip())
    except Exception as e:
        print(f"⚠️ Failed to get duration for {video_path}: {e}")
        return 0.0

# -----------------------------
# 🔐 الجلسة
# -----------------------------
def ensure_telegram_session():
    session_file = BASE_DIR / "session.session"
    if session_file.exists():
        print("✅ Using existing session.session file.")
        return str(session_file)

    b64_file = BASE_DIR / "session.b64"
    if b64_file.exists():
        data = base64.b64decode(b64_file.read_bytes())
        session_file.write_bytes(data)
        os.chmod(session_file, 0o600)
        return str(session_file)

    env_b64 = os.environ.get("TELEGRAM_SESSION_B64")
    if env_b64:
        data = base64.b64decode(env_b64)
        session_file.write_bytes(data)
        os.chmod(session_file, 0o600)
        return str(session_file)

    print("⚠️ No session found.")
    return "session.session"

# -----------------------------
# 🧱 قاعدة بيانات
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
# 📥 تحميل الكرومات القصيرة (≤ 60 ثانية)
# -----------------------------
async def fetch_chromas(api_id, api_hash, channel, session_path):
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()
    conn = init_db()
    c = conn.cursor()
    new_files = []

    MAX_DURATION = 60
    DAILY_LIMIT = 5
    DELAY = 5

    async for msg in client.iter_messages(channel, limit=None):
        if not (msg.video or msg.document):
            continue

        duration = None
        if msg.video and msg.video.attributes:
            for attr in msg.video.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    duration = attr.duration
                    break
        elif msg.document and msg.document.attributes:
            for attr in msg.document.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    duration = attr.duration
                    break

        if not duration or duration > MAX_DURATION:
            continue

        if c.execute("SELECT 1 FROM processed WHERE msg_id=?", (msg.id,)).fetchone():
            continue

        dest = CHROMAS_DIR / f"{msg.id}.mp4"
        print(f"\n⬇️ Downloading short chroma {msg.id} ({round(duration)}s)...")
        try:
            await msg.download_media(file=str(dest))
        except Exception as e:
            print(f"⚠️ Failed to download {msg.id}: {e}")
            continue

        c.execute("INSERT OR REPLACE INTO processed VALUES (?,?,?)",
                  (msg.id, dest.name, datetime.datetime.utcnow().isoformat()))
        conn.commit()
        new_files.append(dest)

        if len(new_files) >= DAILY_LIMIT:
            print("✅ Daily limit reached (5 short chromas).")
            break

        await asyncio.sleep(DELAY)

    await client.disconnect()
    return new_files

# -----------------------------
# 🎬 دمج الكروما مع الخلفية
# -----------------------------
def merge(chroma, bg, output):
    dur = get_duration(chroma)

    # توحيد المقاسات إلى 1080x1920 (9:16)
    chroma_resized = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    bg_resized = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name

    # تغيير مقاس الكروما مع الحفاظ على النسبة
    subprocess.run([
        "ffmpeg", "-y", "-i", str(chroma),
        "-vf", "scale=-1:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-c:a", "copy", chroma_resized
    ], check=True)

    # تغيير مقاس الخلفية بنفس الطريقة وتقطيعها بطول الكروما
    subprocess.run([
        "ffmpeg", "-y", "-i", str(bg), "-t", str(dur),
        "-vf", "scale=-1:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
        "-c:a", "copy", bg_resized
    ], check=True)

    # دمج الكروما والخلفية
    cmd = [
        "ffmpeg", "-y",
        "-i", bg_resized, "-i", chroma_resized,
        "-filter_complex", "[1:v]colorkey=0x000000:0.3:0.2[ck];[0:v][ck]overlay[outv]",
        "-map", "[outv]", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", str(output)
    ]
    subprocess.run(cmd, check=True)

    # تنظيف الملفات المؤقتة
    os.remove(chroma_resized)
    os.remove(bg_resized)

# -----------------------------
# 🚀 Main
# -----------------------------
async def main():
    session_path = ensure_telegram_session()
    conn = init_db()
    drive = get_drive_service()

    print("📥 Fetching new short chromas from Telegram...")
    chromas = await fetch_chromas(api_id, api_hash, channel_username, session_path)
    if not chromas:
        print("⚠️ No new chromas found today.")
        return

    print("☁️ Syncing backgrounds...")
    bg_files = list_drive_files(drive, DRIVE_BG_FOLDER_ID)
    for bg in bg_files:
        dest = BACKGROUND_DIR / bg["name"]
        if not dest.exists():
            download_file(drive, bg["id"], str(dest))

    bg_list = list(BACKGROUND_DIR.glob("*.mp4"))
    log_file = LOGS_DIR / f"uploaded_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt"

    for chroma in chromas:
        out_path = OUTPUTS_DIR / f"final_{chroma.stem}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        try:
            merge(chroma, bg_list, out_path)
            print(f"✅ Created {out_path.name}")
            file_id = upload_file(drive, out_path, DRIVE_OUTPUT_FOLDER_ID)
            print(f"☁️ Uploaded: {file_id}")

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat()} | {out_path.name} | DriveID: {file_id}\n")

            os.remove(chroma)
            os.remove(out_path)
            print(f"🗑️ Deleted {chroma.name} and {out_path.name}")

        except Exception as e:
            print(f"❌ Error with {chroma.name}: {e}")

    conn.close()
    print(f"📝 Log saved to: {log_file}")
    print("🏁 Done!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Script failed:", e)
        sys.exit(1)
