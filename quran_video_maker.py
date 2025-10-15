#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quran Video Maker — v5
- Uses processed.txt and used_titles.txt (no sqlite)
- Daily limit 5 short chromas (<=60s)
- Produces vertical short (720x1280)
- Concatenates multiple backgrounds when needed (no reuse in same run)
- Uploads to Drive with name = title (no .mp4 appended in Drive name)
- Deletes local temp outputs after upload
"""

import os, io, sys, asyncio, random, datetime, tempfile, subprocess, shutil
from pathlib import Path
from telethon import TelegramClient
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# -----------------------------
# 🔧 الإعدادات (عدّل ما يلزم)
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
for d in (CHROMAS_DIR, BACKGROUND_DIR, OUTPUTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

PROCESSED_FILE = BASE_DIR / "processed.txt"           # يحتوي msg_id لكل كرومـا تمت معالجتها
USED_TITLES_FILE = BASE_DIR / "used_titles.txt"      # العناوين المستخدمة سابقًا
HISTORY_LOG = LOGS_DIR / "history.log"

DAILY_LIMIT = 5
MAX_CHROMA_SEC = 60
TARGET_RES = (720, 1280)   # عرض x ارتفاع (شورت عمودي)
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

# عناوين عشوائية
video_titles = [
    "استمتع بسكينة القرآن", "عِش راحة القرآن", "لحظة مع كلام الله", "جمال التلاوة", "نور قلبك بالقرآن",
    "همسات قرآنية", "ترتيل يشرح الصدر", "أنفاس قرآنية", "رحلة مع القرآن", "معاني تطمئن القلب",
    "روعة الصوت القرآني", "طمأنينة من السماء", "قرآن يهز المشاعر", "موسيقى السماء", "صوت الملائكة",
    "صفاء النفس بالقرآن", "ترانيم الرحمة", "آيات تلين القلوب", "نور بين السطور", "سكون القلب",
    "قرآن الشفاء", "خُشوع لا يُوصف", "صوت يحيي الأرواح", "صدى الجنة", "بصوت من الجنة",
    "عيش القرآن بجوارحك", "هدوء القرآن", "نفحات قرآنية", "إيمان متجدد", "تلاوة تذيب القلوب",
    "صوت يهز الوجدان", "لحظة روحانية", "القرآن كما لم تسمعه من قبل", "سافر مع القرآن", "تأمل آية",
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
# ✅ Utilities
# -----------------------------
def load_set_from_file(path):
    if path.exists():
        return set([line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()])
    return set()

def append_line(path, line):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{line}\n")

def ffprobe_duration(path):
    cmd = [FFPROBE, "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(out.stdout.strip())
    except Exception:
        return 0.0

def run_ffmpeg(cmd):
    return subprocess.run(cmd, check=True)

# -----------------------------
# ☁️ Google Drive helpers
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
    files = []
    token = None
    while True:
        res = service.files().list(q=q, spaces='drive', fields='nextPageToken, files(id,name)', pageToken=token).execute()
        files += res.get('files', [])
        token = res.get('nextPageToken')
        if not token:
            break
    return files

def download_file(service, file_id, dest):
    req = service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest, 'wb')
    from googleapiclient.http import MediaIoBaseDownload
    downloader = MediaIoBaseDownload(fh, req)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.close()

def upload_file(service, local_path, drive_folder_id, drive_name):
    media = MediaFileUpload(str(local_path), resumable=True)
    meta = {'name': drive_name, 'parents': [drive_folder_id]}
    file = service.files().create(body=meta, media_body=media, fields='id').execute()
    return file.get('id')

# -----------------------------
# 🎯 Compose background until >= duration (concatenate)
# -----------------------------
def build_background_clip(bg_paths, needed_seconds, used_bg_in_video):
    """
    bg_paths: list of local background file Paths
    needed_seconds: float
    used_bg_in_video: set to record which backgrounds used for this chroma
    returns: path to a temp background mp4 whose duration >= needed_seconds
    """
    chosen = []
    total = 0.0
    available = [p for p in bg_paths if str(p) not in used_bg_in_video]
    # if not enough unique, allow reuse but try avoid
    if not available:
        available = list(bg_paths)
    # shuffle and pick until enough
    random.shuffle(available)
    i = 0
    while total < needed_seconds:
        if i >= len(available):
            # reshuffle and continue (allow reuse if necessary)
            random.shuffle(available)
            i = 0
        p = available[i]
        chosen.append(p)
        dur = ffprobe_duration(p)
        total += dur
        used_bg_in_video.add(str(p))
        i += 1

    # if only one chosen and its duration >= needed => just return it (maybe trimmed)
    temp_list_txt = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt")
    try:
        concat_files = []
        for c in chosen:
            # ensure format compatible for concat: convert to a common codec container in temp if necessary
            concat_files.append(str(c))
            temp_list_txt.write(f"file '{str(c)}'\n")
        temp_list_txt.flush()
    finally:
        temp_list_txt.close()

    out_temp = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name)
    # use ffmpeg concat demuxer
    cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", temp_list_txt.name, "-c", "copy", str(out_temp)]
    try:
        run_ffmpeg(cmd)
    except Exception:
        # fallback: re-encode concat (more robust)
        cmd2 = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", temp_list_txt.name, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", str(out_temp)]
        run_ffmpeg(cmd2)
    os.unlink(temp_list_txt.name)
    return out_temp

# -----------------------------
# 🔁 Merge chroma over background (colorkey)
# -----------------------------
def merge_chroma_and_background(chroma_path, background_path, output_path):
    """
    - Ensure output resolution TARGET_RES
    - Keep chroma content visually intact: scale chroma to fit width (or height) preserving aspect,
      then place centered on 720x1280 background.
    - Use colorkey to remove black (assumes black background) and overlay chroma on background.
    """
    # build filter graphs:
    # 1) scale background to TARGET_RES (may need to loop/truncate background to chroma duration)
    # 2) scale chroma preserving aspect to fit inside TARGET_RES without stretching (use 'scale' with force_original_aspect_ratio)
    # 3) apply colorkey on chroma and overlay
    dur = ffprobe_duration(chroma_path)
    bg_scaled = str(background_path)

    cmd = [
        FFMPEG, "-y",
        "-i", bg_scaled,
        "-i", str(chroma_path),
        "-filter_complex",
        # scale background, scale chroma to fit (force_original_aspect_ratio=decrease), pad chroma to target centered, then colorkey + overlay
        (
            f"[0:v]scale={TARGET_RES[0]}:{TARGET_RES[1]}:force_original_aspect_ratio=decrease,pad={TARGET_RES[0]}:{TARGET_RES[1]}:(ow-iw)/2:(oh-ih)/2[bg];"
            f"[1:v]scale=w={TARGET_RES[0]}:h={TARGET_RES[1]}:force_original_aspect_ratio=increase,scale='min(iw,{TARGET_RES[0]})':'min(ih,{TARGET_RES[1]})',pad={TARGET_RES[0]}:{TARGET_RES[1]}:(ow-iw)/2:(oh-ih)/2[ch];"
            f"[ch]colorkey=0x000000:0.3:0.15[ck];[bg][ck]overlay=0:0[outv]"
        ),
        "-map", "[outv]",
        "-map", "1:a?",   # use chroma audio if present
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(dur),
        str(output_path)
    ]
    run_ffmpeg(cmd)

# -----------------------------
# 📥 Fetch chromas (Telethon)
# -----------------------------
async def fetch_chromas(api_id, api_hash, channel, session_path):
    client = TelegramClient(session_path, api_id, api_hash)
    await client.start()
    existing = load_set_from_file(PROCESSED_FILE)
    new_files = []
    count = 0
    async for msg in client.iter_messages(channel, limit=None):
        if count >= DAILY_LIMIT:
            break

        # figure out video and duration
        if getattr(msg, "video", None):
            video = msg.video
            dur = getattr(video, "duration", None)
        elif getattr(msg, "document", None) and getattr(msg.document, "mime_type", "").startswith("video/"):
            video = msg.document
            dur = None
            for a in getattr(video, "attributes", []):
                if getattr(a, "duration", None):
                    dur = a.duration
                    break
        else:
            continue

        if dur is None:
            continue
        if dur > MAX_CHROMA_SEC:
            continue

        if str(msg.id) in existing:
            continue

        dest = CHROMAS_DIR / f"{msg.id}.mp4"
        print(f"\n⬇️ Downloading short chroma {msg.id} ({dur}s)...")
        # try download
        for attempt in range(3):
            try:
                await msg.download_media(file=str(dest))
                break
            except Exception as e:
                print("⚠️ download retry:", e)
                await asyncio.sleep(5)
        if not dest.exists():
            print("❌ Failed to download:", msg.id)
            continue

        append_line(PROCESSED_FILE, str(msg.id))
        new_files.append(dest)
        count += 1
        await asyncio.sleep(1)
    await client.disconnect()
    return new_files

# -----------------------------
# 🔁 Main flow
# -----------------------------
async def main():
    # ensure ffmpeg/ffprobe existence
    if shutil.which(FFMPEG) is None or shutil.which(FFPROBE) is None:
        print("❌ ffmpeg/ffprobe not found in PATH. Please install them.")
        return

    session_path = BASE_DIR / "session.session"
    if not session_path.exists():
        b64 = os.environ.get("TELEGRAM_SESSION_B64")
        if b64:
            session_path.write_bytes(__import__("base64").b64decode(b64))
        else:
            print("⚠️ session.session not found. Telethon may prompt for login.")
    print("Session ready:", session_path)

    drive = get_drive_service()

    print("📥 Fetching new short chromas from Telegram...")
    chromas = await fetch_chromas(api_id, api_hash, channel_username, str(session_path))
    if not chromas:
        print("⚠️ No new chromas found.")
        return

    print("☁️ Syncing backgrounds from Drive folder...")
    bg_files_meta = list_drive_files(drive, DRIVE_BG_FOLDER_ID)
    if not bg_files_meta:
        print("❌ No backgrounds in Drive folder.")
        return

    # Download backgrounds locally if not present
    for meta in bg_files_meta:
        local = BACKGROUND_DIR / meta["name"]
        if not local.exists():
            print("⬇️ Downloading background", meta["name"])
            try:
                download_file(drive, meta["id"], str(local))
            except Exception as e:
                print("⚠️ download background failed:", e)

    bg_list = list(BACKGROUND_DIR.glob("*"))
    if not bg_list:
        print("❌ No local backgrounds available.")
        return

    used_titles = load_set_from_file(USED_TITLES_FILE)
    used_bg_session = set()  # backgrounds used in this run (prevent reuse inside batch)
    created = 0

    # shuffle chromas so selection is random order
    random.shuffle(chromas)

    for chroma_path in chromas[:DAILY_LIMIT]:
        # choose a title not used before
        available_titles = [t for t in video_titles if t not in used_titles]
        if not available_titles:
            # if exhausted all, allow reuse but avoid immediate repeats
            available_titles = video_titles.copy()
        title = random.choice(available_titles)
        used_titles.add(title)
        append_line(USED_TITLES_FILE, title)

        # ensure backgrounds chosen randomly (and not repeated within the 5)
        used_bg_in_video = set()
        needed_seconds = ffprobe_duration(chroma_path)
        bg_clip = build_background_clip(bg_list, needed_seconds, used_bg_in_video)
        # mark backgrounds used globally in this session (avoid reuse across videos in batch)
        for u in used_bg_in_video:
            used_bg_session.add(u)

        # prepare local output filename (temporary)
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
        local_out = OUTPUTS_DIR / f"{safe_title}.mp4"

        print(f"🎞 Producing final for '{title}' ...")
        try:
            merge_chroma_and_background(chroma_path, bg_clip, local_out)
            # upload to Drive with name = title (without .mp4 as requested)
            drive_name = title  # as requested, no .mp4 appended
            file_id = upload_file(drive, local_out, DRIVE_OUTPUT_FOLDER_ID, drive_name)
            append_line(HISTORY_LOG, f"{datetime.datetime.utcnow().isoformat()} | {chroma_path.name} -> {drive_name} | {file_id}")
            print(f"☁️ Uploaded: {file_id} (as '{drive_name}')")
            created += 1
        except Exception as e:
            print("❌ Error with", chroma_path.name, ":", e)
        finally:
            # cleanup
            try:
                if bg_clip and bg_clip.exists():
                    bg_clip.unlink()
            except Exception:
                pass
            try:
                if local_out.exists():
                    local_out.unlink()
            except Exception:
                pass

    print("🏁 Done. Created:", created)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("❌ Script failed:", e)
        sys.exit(1)
