# Video Blend - Headless CI

كيفية التشغيل:

## محلياً
1. ضع فيديوهات foreground في `input_videos/`
2. ضع فيديوهات background في `background_videos/`
3. ثبت ffmpeg و Python dependencies:
   ```bash
   sudo apt-get install ffmpeg
   pip install -r requirements.txt
   ./run_local.sh
