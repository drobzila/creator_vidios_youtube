#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Quran Video Maker (updated to accept base64 session)
- Uses session.session if present.
- Else tries to decode session.b64 in repo root.
- Else tries TELEGRAM_SESSION_B64 env var (Base64).
Security: do NOT commit session.session or session.b64 to a public repo.
"""

import os
import sys
import sqlite3
import asyncio
import random
import datetime
import shutil
import subprocess
import tempfile
from pathlib import Path
import base64

# Telethon for Telegram access
from telethon import TelegramClient

# Google Drive API
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.oauth2.credentials import Credentials
import io

# ---------------------------
# Configuration (user provided)
# ---------------------------
api_id = 27874350
api_hash = "a8cca90ec7d1023b8118163822f187c0"
channel_username = "quranbng"

# OAuth client credentials and refresh token (user provided)
CLIENT_ID = "553805965519-1gvas0tmcl86v76k7m9bhkmc7m76657s.apps.googleusercontent.com"
CLIENT_SECRET = "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"
REFRESH_TOKEN = "1//09SLS4A1oZYsJCgYIARAAGAkSNwF-L9IrQJneNmOVOAjihJWVMGFL2gYlLAdg0Y_0SZg4bQPjbRR-qkDKYvbSS4weE7zrPh8w4_E"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Drive folders (IDs from your links)
DRIVE_BG_FOLDER_ID = "1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C"
DRIVE_OUTPUT_FOLDER_ID = "1lLKbFPovufWeEkwpCgI3cM-Je-Uee9el"

# Local directories
BASE_DIR = Path.cwd()
CHROMAS_DIR = BASE_DIR / "chromas"
BACKGROUND_DIR = BASE_DIR / "background_videos"
OUTPUTS_DIR = BASE_DIR / "outputs"
LOGS_DIR = BASE_DIR / "output_logs"
DB_PATH = BASE_DIR / "processed.db"

# ffmpeg settings
FFMPEG_BIN = "ffmpeg"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"
PRESET = "veryfast"
CRF = "23"

MAX_CHROMA_SEC = 60

for d in (CHROMAS_DIR, BACKGROUND_DIR, OUTPUTS_DIR, LOGS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------
# Session handling helpers
# ---------------------------
def ensure_telegram_session():
    """
    Ensure a usable 'session.session' file exists for Telethon.
    Priority:
      1) session.session file exists -> use it
      2) session.b64 file exists in repo root -> decode to session.session
      3) TELEGRAM_SESSION_B64 env var exists -> decode
    Returns path to session file (string) or None if not found.
    """
    session_bin = BASE_DIR / "session.session"
    session_b64_file = BASE_DIR / "session.b64"

    if session_bin.exists():
        print("Using existing session.session file.")
        return str(session_bin)

    # 2) session.b64 file in repo root
    if session_b64_file.exists():
        print("Found session.b64 file in repo root — decoding to session.session")
        try:
            data = session_b64_file.read_bytes()
            # may already be base64 text; decode
            decoded = base64.b64decode(data)
            session_bin.write_bytes(decoded)
            # set permissions
            try:
                os.chmod(session_bin, 0o600)
            except:
                pass
            return str(session_bin)
        except Exception as e:
            print("Failed to decode session.b64:", e)

    # 3) TELEGRAM_SESSION_B64 env var
    env_b64 = os.environ.get("TELEGRAM_SESSION_B64")
    if env_b64:
        print("Decoding TELEGRAM_SESSION_B64 env var to session.session")
        try:
            decoded = base64.b64decode(env_b64)
            session_bin.write_bytes(decoded)
            try:
                os.chmod(session_bin, 0o600)
            except:
                pass
            return str(session_bin)
        except Exception as e:
            print("Failed to decode TELEGRAM_SESSION_B64:", e)

    print("No session.session / session.b64 / TELEGRAM_SESSION_B64 found. Telethon will try interactive login.")
    return None

# ---------------------------
# Database helpers (unchanged)
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS processed_tele (
        msg_id INTEGER PRIMARY KEY,
        file_name TEXT,
        processed_at TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS uploaded_outputs (
        file_name TEXT PRIMARY KEY,
        drive_file_id TEXT,
        uploaded_at TEXT
    )""")
    conn.commit()
    return conn

# (The rest of the functions: get_drive_service, list_files_in_folder, download_file_from_drive,
#  upload_file_to_drive, fetch_chromas_from_telegram, merge_chroma_over_bg, and main remain
#  functionally the same as in the previous full script you were given.)

# For brevity, include them unchanged below (copy-paste the implementations from the previous script),
# but ensure fetch_chromas_from_telegram uses the session path returned by ensure_telegram_session().

# ---------------------------
# Telethon (Telegram) helpers (updated to use session path)
# ---------------------------
async def fetch_chromas_from_telegram(api_id, api_hash, channel_username, limit=50, session_path=None):
    """
    Downloads video messages from the channel that: video and duration <= MAX_CHROMA_SEC
    Saves to chromas/ directory as <msg_id>.mp4
    If session_path is provided, use it as the Telethon session filename.
    """
    session_name = session_path if session_path else "session_telegram"
    client = TelegramClient(str(session_name), api_id, api_hash)
    await client.start()
    downloaded = []
    try:
        async for msg in client.iter_messages(channel_username, limit=limit):
            if not msg:
                continue
            if msg.video and msg.video.duration and msg.video.duration <= MAX_CHROMA_SEC:
                msg_id = msg.id
                conn = sqlite3.connect(DB_PATH)
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM processed_tele WHERE msg_id=?", (msg_id,))
                if cur.fetchone():
                    conn.close()
                    continue
                conn.close()

                filename = CHROMAS_DIR / f"{msg_id}.mp4"
                if filename.exists():
                    downloaded.append(filename)
                    continue
                print(f"Downloading Telegram message {msg_id} (duration {msg.video.duration}s)...")
                await msg.download_media(file=str(filename))
                downloaded.append(filename)
    finally:
        await client.disconnect()
    return downloaded

# ---------------------------
# (Place here the rest of helper functions and main flow identical to earlier script)
# For brevity in this message I keep them as-is; when you paste into your repo,
# ensure you include get_drive_service, list_files_in_folder, download/upload, merge_chroma_over_bg, main, etc.
# ---------------------------

# Example main runner (short form) - integrate full logic from previous script:
async def main():
    session_path = ensure_telegram_session()
    # proceed with rest of logic, passing session_path to fetch_chromas_from_telegram(...)
    # (copy the rest of the main flow from the previous full script)
    print("Session prepared at:", session_path)
    # ... (download backgrounds, merge, upload, db updates)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("Script failed:", e)
        sys.exit(1)
