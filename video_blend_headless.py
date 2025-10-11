#!/usr/bin/env python3
"""
Headless video blender with optional automatic background download.

Usage example:
  python3 video_blend_headless.py \
      --input1_dir input_videos \
      --input2_dir background_videos \
      --output_dir outputs
"""

import os
import argparse
import random
import subprocess
from moviepy.editor import VideoFileClip, CompositeVideoClip


DEFAULT_DRIVE_URL = "https://drive.google.com/drive/folders/1JYb3bI1PFJIHCPm8Vwm26b6vX7w5gL_C?usp=sharing"


def blend_videos(foreground_path, background_path, output_path):
    """Blend one foreground video over one background video."""
    try:
        fg = VideoFileClip(foreground_path, has_mask=True)
        bg = VideoFileClip(background_path)

        # Resize background to match foreground height
        bg = bg.resize(height=fg.h)

        # Clip both to same duration
        min_dur = min(fg.duration, bg.duration)
        fg = fg.subclip(0, min_dur)
        bg = bg.subclip(0, min_dur)

        # Overlay foreground over background
        comp = CompositeVideoClip([bg, fg.set_position("center")])
        comp.write_videofile(output_path, codec="libx264", audio_codec="aac", threads=4, preset="medium")
        fg.close(); bg.close(); comp.close()
    except Exception as e:
        print(f"⚠️ Error blending {foreground_path} + {background_path}: {e}")


def ensure_backgrounds(background_dir, drive_folder_url):
    """Ensure background videos exist locally; if missing, download from Drive."""
    bg_videos = [os.path.join(background_dir, f) for f in os.listdir(background_dir)
                 if f.lower().endswith((".mp4", ".mov", ".mkv"))]

    if bg_videos:
        return bg_videos

    print("⚠️ No background videos found. Trying to download from Google Drive...")
    if drive_folder_url:
        try:
            subprocess.run(["gdown", "--folder", drive_folder_url, "-O", background_dir], check=True)
        except subprocess.CalledProcessError:
            print("⚠️ gdown download failed — continuing without backgrounds.")
        bg_videos = [os.path.join(background_dir, f) for f in os.listdir(background_dir)
                     if f.lower().endswith((".mp4", ".mov", ".mkv"))]
    return bg_videos


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input1_dir", required=True, help="Directory with foreground/input videos")
    parser.add_argument("--input2_dir", required=True, help="Directory with background videos")
    parser.add_argument("--output_dir", required=True, help="Directory to save blended videos")
    parser.add_argument("--bg_per_effect", type=int, default=3, help="How many backgrounds to combine per foreground")
    parser.add_argument("--compress", type=str, default="true", help="Compress output videos with ffmpeg")
    parser.add_argument("--crf", type=int, default=28, help="Compression quality (lower = better quality)")
    parser.add_argument("--drive_folder_url", default="", help="Optional Google Drive folder URL for backgrounds")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.input2_dir, exist_ok=True)

    # Use built-in Drive URL if not passed
    drive_folder_url = args.drive_folder_url or os.environ.get("DRIVE_FOLDER_URL") or DEFAULT_DRIVE_URL

    fg_videos = [os.path.join(args.input1_dir, f) for f in os.listdir(args.input1_dir)
                 if f.lower().endswith((".mp4", ".mov", ".mkv"))]

    if not fg_videos:
        print("❌ No input videos found in", args.input1_dir)
        return

    bg_videos = ensure_backgrounds(args.input2_dir, drive_folder_url)
    if not bg_videos:
        print("❌ No background videos available. Exiting.")
        return

    for fg in fg_videos:
        chosen_bgs = random.sample(bg_videos, min(args.bg_per_effect, len(bg_videos)))
        for bg in chosen_bgs:
            base = os.path.splitext(os.path.basename(fg))[0]
            out_name = f"{base}__{os.path.basename(bg)}"
            out_path = os.path.join(args.output_dir, out_name)

            print(f"🎞️ Blending {os.path.basename(fg)} with {os.path.basename(bg)} ...")
            blend_videos(fg, bg, out_path)

            if args.compress.lower() == "true":
                compressed = out_path.replace(".mp4", "_crf.mp4")
                subprocess.run(["ffmpeg", "-y", "-i", out_path, "-vcodec", "libx264",
                                "-crf", str(args.crf), "-preset", "faster", compressed])
                os.remove(out_path)
                os.rename(compressed, out_path)

    print("✅ All blends completed successfully.")


if __name__ == "__main__":
    main()
