#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📽️ Quran Video Maker — Auto short chromas downloader (≤ 60s)
By Mohamed — Works with GitHub Actions
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
# 🔧 إعدادات من متغيرات البيئة (Secrets)
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
# 🔐 إنشاء جلسة التلغرام
# -----------------------------
def ensure_telegram_session():
    session_file = BASE_DIR / "session.session"
    if session_file.exists():
        print("✅ Using existing session.session file.")
        return str(session_file)

    b64_data = os.getenv("TELEGRAM_SESSION_B64")
    if b64_data:
        data = base64.b64decode(b64_data)
        session_file.write_bytes(data)
        os.chmod(session_file, 0o600)
        print("✅ Telegram session restored from Base64 secret.")
        return str(session_file)

    print("⚠️ No Telegram session found.")
    return str(session_file)

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
# 📥 تحميل كرومات قصيرة من التلغرام
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
        attrs = msg.video.attributes if msg.video else msg.document.attributes
        for attr in attrs:
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
            print("✅ Daily limit reached.")
            break

        await asyncio.sleep(DELAY)

    await client.disconnect()
    return new_files

# -----------------------------
# 🎬 دمج الكروما مع الخلفية
# -----------------------------
def get_duration(path):
    """📏 استخراج مدة الفيديو بالثواني"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ]
    out = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except:
        return 0.0


def merge(chroma, bg, output):
    """🎬 دمج الكروما والخلفية بحجم فيديو شورت (1080x1920)"""
    dur = get_duration(chroma)

    # مؤقت للخلفية
    tmp_bg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(bg),
        "-t", str(dur),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an", tmp_bg
    ], check=True)

    # مؤقت للكروما
    tmp_chroma = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run([
        "ffmpeg", "-y",
        "-i", str(chroma),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-an", tmp_chroma
    ], check=True)

    # دمج نهائي
    cmd = [
        "ffmpeg", "-y",
        "-i", tmp_bg, "-i", tmp_chroma,
        "-filter_complex",
        "[1:v]colorkey=0x000000:0.3:0.2[ck];[0:v][ck]overlay[outv]",
        "-map", "[outv]", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", str(output)
    ]
    subprocess.run(cmd, check=True)

    os.remove(tmp_bg)
    os.remove(tmp_chroma)
    
# -----------------------------
# 🚀 Main
# -----------------------------
async def main():
    print("🚀 Quran Video Maker started.")
    session_path = ensure_telegram_session()
    conn = init_db()
    drive = get_drive_service()

    print("📥 Fetching new short chromas from Telegram...")
    chromas = await fetch_chromas(api_id, api_hash, channel_username, session_path)
    if not chromas:
        print("⚠️ No new chromas found today.")
        return

    print("☁️ Syncing backgrounds from Google Drive...")
    bg_files = list_drive_files(drive, DRIVE_BG_FOLDER_ID)
    for bg in bg_files:
        dest = BACKGROUND_DIR / bg["name"]
        if not dest.exists():
            print(f"⬇️ Downloading background: {bg['name']}")
            download_file(drive, bg["id"], str(dest))

    bg_list = list(BACKGROUND_DIR.glob("*.mp4"))
    for chroma in chromas:
        bg = random.choice(bg_list)
        out_path = OUTPUTS_DIR / f"final_{chroma.stem}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        try:
            merge(chroma, bg, out_path)
            print(f"✅ Created {out_path.name}")
            file_id = upload_file(drive, out_path, DRIVE_OUTPUT_FOLDER_ID)
            print(f"☁️ Uploaded: {file_id}")
        except Exception as e:
            print(f"❌ Error with {chroma.name}: {e}")

    conn.close()
    print("🏁 Done!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Script failed:", e)
        sys.exit(1)
