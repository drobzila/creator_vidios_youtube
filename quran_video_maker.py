#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
📽️ Quran Video Maker — Viral Optimized (≤ 20s) + Multi-background
By Mohamed — Optimized for Shorts / Reels / TikTok
"""

import os, io, sys, base64, asyncio, random, datetime, tempfile, subprocess
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.types import DocumentAttributeVideo
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# -----------------------------
# 🔧 الإعدادات
# -----------------------------
api_id = 27874350
api_hash = "a8cca90ec7d1023b8118163822f187c0"
channel_username = "quranbng"

CLIENT_ID = "108880269998-bcjare6v388kucan7amb82q370m61pq5.apps.googleusercontent.com" 
CLIENT_SECRET = "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" 
REFRESH_TOKEN = "1//03JHjFKSZ6V56CgYIARAAGAMSNwF-L9Ir4ZVvnpbx64vKup8pkXuspIxGBlmEAguJjweg6hzYGjU8U4l_oGLZJuArjcqRSW2HTB0" 
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive"]

DRIVE_BG_FOLDER_ID = "1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C"
DRIVE_OUTPUT_FOLDER_ID = "1lLKbFPovufWeEkwpCgI3cM-Je-Uee9el"
BASE_DIR = Path.cwd()
CHROMAS_DIR = BASE_DIR / "chromas"
BACKGROUND_DIR = BASE_DIR / "background_videos"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOG_FILE = BASE_DIR / "log.txt"

for d in (CHROMAS_DIR, BACKGROUND_DIR, OUTPUTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# -----------------------------
# 🔐 جلسة التلغرام
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
    return build("drive", "v3", credentials=creds, cache_discovery=False)

def list_drive_files(service, folder_id):
    q = f"'{folder_id}' in parents and trashed=false"
    files, token = [], None
    while True:
        res = service.files().list(q=q, spaces="drive", fields="nextPageToken, files(id,name)", pageToken=token).execute()
        files += res.get("files", [])
        token = res.get("nextPageToken")
        if not token:
            break
    return files

def download_file(service, file_id, dest):
    req = service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest, "wb")
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.close()

def upload_file(service, path, folder_id):
    meta = {"name": path.name, "parents": [folder_id]}
    media = MediaFileUpload(str(path), resumable=True)
    file = service.files().create(body=meta, media_body=media, fields="id").execute()
    return file["id"]

# -----------------------------
# 📥 تحميل كرومات قصيرة من التلغرام
# -----------------------------
async def fetch_chromas(api_id, api_hash, channel, session_path):
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()

    used_ids = set()
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "msg_id=" in line:
                    try:
                        used_ids.add(int(line.split("msg_id=")[-1].strip()))
                    except:
                        continue

    print(f"📜 {len(used_ids)} chromas already used (by msg.id).")
    new_files = []
    MAX_DURATION = 20  # optimized for Shorts
    DAILY_LIMIT = 5
    DELAY = 5

    async for msg in client.iter_messages(channel, limit=None):
        if not (msg.video or msg.document):
            continue
        if msg.id in used_ids:
            continue

        duration = None
        try:
            attrs = msg.video.attributes if msg.video else msg.document.attributes
            for attr in attrs:
                if isinstance(attr, DocumentAttributeVideo):
                    duration = attr.duration
                    break
        except Exception:
            pass

        if duration and duration > MAX_DURATION:
            continue

        fname = msg.file.name or f"chroma_{msg.id}.mp4"
        dest = CHROMAS_DIR / fname.replace(" ", "_").replace("/", "_")

        try:
            await msg.download_media(file=str(dest))
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{now} - استخدمت الكروما: {fname} | msg_id={msg.id}\n")
            new_files.append(dest)
        except:
            continue

        if len(new_files) >= DAILY_LIMIT:
            break

        await asyncio.sleep(DELAY)

    await client.disconnect()
    return new_files

# -----------------------------
# ⏱️ حساب مدة الفيديو
# -----------------------------
def get_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except:
        return 0.0

# -----------------------------
# 🎬 دمج + تحسين للفيديوهات المنتشرة
# -----------------------------
def merge(chroma, bg_list, output):
    chroma_dur = get_duration(chroma)
    if chroma_dur <= 0:
        return

    # اختيار خلفية أو أكثر لتغطية طول الكروما
    valid_bgs = [b for b in bg_list if get_duration(b) > 0]
    if not valid_bgs:
        return

    selected_bgs = []
    total_duration = 0
    while total_duration < chroma_dur:
        bg = random.choice(valid_bgs)
        selected_bgs.append(bg)
        total_duration += get_duration(bg)

    # دمج الخلفيات مع Crossfade
    bg_list_txt = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt")
    for bg in selected_bgs:
        bg_list_txt.write(f"file '{bg.resolve()}'\n")
    bg_list_txt.close()

    tmp_bg = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", bg_list_txt.name, "-c", "copy", tmp_bg], check=True)
    os.remove(bg_list_txt.name)

    tmp_bg_scaled = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_bg,
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,vignette=PI/4",
        "-preset", "fast", "-crf", "23", tmp_bg_scaled
    ], check=True)
    os.remove(tmp_bg)

    # تجهيز الكروما
    tmp_chroma = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run([
        "ffmpeg", "-y", "-i", str(chroma),
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,eq=contrast=1.1:saturation=1.15:brightness=0.02",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", tmp_chroma
    ], check=True)

    # دمج الكروما مع الخلفية
    tmp_final = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False).name
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_bg_scaled, "-i", tmp_chroma,
        "-filter_complex", "[1:v]colorkey=0x000000:0.3:0.2[ck];[0:v][ck]overlay[outv]",
        "-map", "[outv]", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", tmp_final
    ], check=True)

    # إضافة نص آية متحرك في منتصف الفيديو (Hook + Captions)
    subprocess.run([
        "ffmpeg", "-y", "-i", tmp_final,
        "-vf", "drawtext=text='﴿ إِنَّ مَعَ الْعُسْرِ يُسْرًا ﴾':fontfile=Amiri-Bold.ttf:fontsize=64:fontcolor=white:x=(w-text_w)/2:y=h*0.75:box=1:boxcolor=black@0.4:boxborderw=20:enable='between(t,0,5)'",
        "-c:a", "copy", str(output)
    ], check=True)

    os.remove(tmp_bg_scaled)
    os.remove(tmp_chroma)
    os.remove(tmp_final)

# -----------------------------
# 🚀 Main
# -----------------------------
async def main():
    session_path = ensure_telegram_session()
    drive = get_drive_service()

    chromas = await fetch_chromas(api_id, api_hash, channel_username, session_path)
    if not chromas:
        print("⚠️ No new chromas today.")
        return

    # Sync backgrounds
    bg_files = list_drive_files(drive, DRIVE_BG_FOLDER_ID)
    for bg in bg_files:
        dest = BACKGROUND_DIR / bg["name"]
        if not dest.exists():
            download_file(drive, bg["id"], str(dest))

    bg_list = list(BACKGROUND_DIR.glob("*.mp4"))
    for chroma in chromas:
        out_path = OUTPUTS_DIR / f"viral_{chroma.stem}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        try:
            merge(chroma, bg_list, out_path)
            fid = upload_file(drive, out_path, DRIVE_OUTPUT_FOLDER_ID)
            print(f"✅ Created & uploaded {out_path.name} -> {fid}")
        except Exception as e:
            print(f"❌ Error {chroma.name}: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Script failed:", e)
        sys.exit(1)
