#!/usr/bin/env python3
"""
Headless video blender with optional Google Drive folder download.

Usage examples:
  # local already-downloaded:
  python3 video_blend_headless.py --input1_dir input_videos --input2_dir background_videos --output_dir outputs

  # with Drive folder URL (will download into background_videos/)
  export DRIVE_FOLDER_URL="https://drive.google.com/drive/folders/1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C?usp=sharing"
  python3 video_blend_headless.py --input1_dir input_videos --input2_dir background_videos --output_dir outputs
"""
import os
import sys
import argparse
import random
import subprocess
import cv2
import numpy as np
from pathlib import Path

# try import gdown (optional)
try:
    import gdown
    GDOWN_AVAILABLE = True
except Exception:
    GDOWN_AVAILABLE = False

VIDEO_TITLES = [
    # ... (ضع هنا نفس قائمة العناوين التي استخدمتها سابقًا) ...
    "استمتع بسكينة القرآن", "عِش راحة القرآن", "لحظة مع كلام الله", "جمال التلاوة", "نور قلبك بالقرآن",
    "همسات قرآنية", "ترتيل يشرح الصدر", "أنفاس قرآنية", "رحلة مع القرآن", "معاني تطمئن القلب",
    "روعة الصوت القرآني", "طمأنينة من السماء", "قرآن يهز المشاعر", "موسيقى السماء", "صوت الملائكة",
    # ... اكمل باقي العناوين كما في النسخة الأصلية ...
]
used_titles = set()
TARGET_SIZE = (720, 1280)

def download_drive_folder(folder_url, target_dir):
    """
    Uses gdown to download an entire folder by URL (requires folder to be shared).
    gdown supports `--folder` option.
    """
    if not GDOWN_AVAILABLE:
        raise RuntimeError("gdown غير مثبت. ثبته عبر: pip install gdown")
    os.makedirs(target_dir, exist_ok=True)
    print(f"[INFO] تنزيل محتوى Google Drive من: {folder_url} إلى {target_dir} ...")
    # gdown.download_folder(folder_url, output=target_dir, quiet=False)  # older API
    # Use subprocess to call gdown CLI for robust behavior
    cmd = ["gdown", "--folder", folder_url, "-O", target_dir]
    subprocess.run(cmd, check=True)
    print("[OK] الانتهاء من تنزيل Drive.")

def get_video_frames(path, target_frames):
    cap = cv2.VideoCapture(path)
    frames = []
    while len(frames) < target_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame = cv2.resize(frame, TARGET_SIZE)
        frames.append(frame)
    cap.release()
    return frames

def get_video_frames_repeat(paths, target_frames):
    frames = []
    for path in paths:
        if len(frames) >= target_frames:
            break
        available_frames = get_video_frames(path, target_frames - len(frames))
        frames.extend(available_frames)
    return frames[:target_frames]

def add_audio(source_path, target_path, output_path):
    command = [
        "ffmpeg", "-y",
        "-i", target_path,
        "-i", source_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a:0",
        output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def compress_video(input_path, output_path, crf):
    command = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vcodec", "libx264",
        "-crf", str(crf),
        "-preset", "medium",
        "-acodec", "aac",
        "-b:a", "128k",
        output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def blend_single_video(video1_path, video2_paths, output_folder, result_index, compress, crf):
    global used_titles
    available_titles = list(set(VIDEO_TITLES) - used_titles)
    if not available_titles:
        selected_title = f"فيديو_قرآني_{result_index}"
    else:
        selected_title = random.choice(available_titles)
        used_titles.add(selected_title)

    safe_title = "".join(c for c in selected_title if c.isalnum() or c in " _-").strip()
    filename = f"{safe_title}.mp4"
    final_output = os.path.join(output_folder, filename)

    cap1 = cv2.VideoCapture(video1_path)
    fps = int(cap1.get(cv2.CAP_PROP_FPS)) or 25
    total_frames = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    if total_frames == 0:
        print(f"[WARN] لم يتم قراءة أي فريمات من {video1_path}. تخطي.")
        cap1.release()
        return

    background_frames = get_video_frames_repeat(video2_paths, total_frames)
    if len(background_frames) < total_frames:
        print(f"[WARN] الخلفيات قصيرة بالنسبة لـ {video1_path}. سيتم ملؤها بالتكرار الجزئي.")

    temp_output = f"temp_output_{result_index}.mp4"
    temp_with_audio = f"temp_with_audio_{result_index}.mp4"

    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(temp_output, fourcc, fps, TARGET_SIZE)

    for i in range(total_frames):
        ret1, frame1 = cap1.read()
        if not ret1:
            break
        h1, w1 = frame1.shape[:2]
        scale = min(TARGET_SIZE[0] / w1, TARGET_SIZE[1] / h1, 1.0)
        new_w = int(w1 * scale)
        new_h = int(h1 * scale)
        frame1_resized = cv2.resize(frame1, (new_w, new_h))
        x_offset = (TARGET_SIZE[0] - new_w) // 2
        y_offset = (TARGET_SIZE[1] - new_h) // 2
        # get background frame safely
        bg_frame = background_frames[i % len(background_frames)].copy()
        roi = bg_frame[y_offset:y_offset+new_h, x_offset:x_offset+new_w]
        blended_roi = np.maximum(roi, frame1_resized)
        bg_frame[y_offset:y_offset+new_h, x_offset:x_offset+new_w] = blended_roi
        out.write(bg_frame)

    cap1.release()
    out.release()

    add_audio(video1_path, temp_output, temp_with_audio)

    if compress:
        compress_video(temp_with_audio, final_output, crf)
        if os.path.exists(temp_with_audio):
            os.remove(temp_with_audio)
    else:
        os.replace(temp_with_audio, final_output)

    if os.path.exists(temp_output):
        os.remove(temp_output)

    print(f"[OK] أنشئ: {final_output}")

def collect_video_files(folder):
    p = Path(folder)
    if not p.exists():
        return []
    return sorted([str(x) for x in p.iterdir() if x.suffix.lower() in ('.mp4','.mov','.avi')])

def main():
    parser = argparse.ArgumentParser(description="Headless video blender")
    parser.add_argument("--input1_dir", required=True, help="مجلد فيديوهات foreground")
    parser.add_argument("--input2_dir", required=True, help="مجلد فيديوهات background")
    parser.add_argument("--output_dir", required=True, help="مجلد حفظ الفيديوهات الناتجة")
    parser.add_argument("--bg_per_effect", type=int, default=3)
    parser.add_argument("--compress", type=str, default="true", help="true/false")
    parser.add_argument("--crf", type=int, default=28)
    parser.add_argument("--drive_folder_url", type=str, default=None, help="(اختياري) رابط مجلد Google Drive لتحميل الخلفيات")
    args = parser.parse_args()

    # إذا أعطيت رابط Drive، نحاول تنزيله
    if args.drive_folder_url:
        if not GDOWN_AVAILABLE:
            print("[ERROR] gdown غير مثبت. ثبت dependencies أولاً (pip install -r requirements.txt).")
            sys.exit(1)
        try:
            download_drive_folder(args.drive_folder_url, args.input2_dir)
        except Exception as e:
            print(f"[ERROR] فشل تنزيل Drive: {e}")
            sys.exit(1)

    input1_files = collect_video_files(args.input1_dir)
    input2_files = collect_video_files(args.input2_dir)

    if not input1_files or not input2_files:
        print("[ERROR] تأكد من وجود ملفات في المجلدات input1_dir و input2_dir.")
        sys.exit(1)
    os.makedirs(args.output_dir, exist_ok=True)

    bg_pointer = 0
    for idx, v1 in enumerate(input1_files):
        if idx % args.bg_per_effect == 0:
            bg_index = bg_pointer % len(input2_files)
            main_bg = input2_files[bg_index]
            bg_pointer += 1
        background_list = input2_files[bg_index+1:] + input2_files[:bg_index]
        selected_bgs = [main_bg] + list(background_list)
        blend_single_video(v1, selected_bgs, args.output_dir, idx+1, args.compress.lower() == "true", args.crf)

if __name__ == "__main__":
    main()
