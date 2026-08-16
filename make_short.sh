#!/usr/bin/env bash
# make_short.sh - 一键生成短视频（自适应时长）
# 用法: bash make_short.sh [主题音频文件.mp3] [输出文件名.mp4]
# 默认: bash make_short.sh  →  voiceover_full.mp3 → final.mp4
# 示例: bash make_short.sh voiceover_t2.mp3 final_t2.mp4
# 配置: 修改 script.txt 即可换主题（封面/字幕/水印）
#
# Pipeline: 解析 script.txt → 检测音频时长 → 合成 BGM → ASCII 视觉层
#           → 渐变背景 → 烧 drawtext 字幕 → 合成 final.mp4

set -e
cd "$(dirname "$0")"

FONT="C\\:/Windows/Fonts/simhei.ttf"
W=720
H=1280
FPS=30

# ---- 参数解析 ----
INPUT_AUDIO="${1:-voiceover_full.mp3}"
OUTPUT_VIDEO="${2:-final.mp4}"

echo "=== make_short.sh ==="
echo "[input] $INPUT_AUDIO"
echo "[output] $OUTPUT_VIDEO"

# ---- 1. 解析 script.txt ----
COVER_MAIN=$(grep '^COVER_MAIN' script.txt | cut -d'|' -f2)
COVER_SUB=$(grep '^COVER_SUB' script.txt | cut -d'|' -f2)
WATERMARK=$(grep '^WATERMARK' script.txt | cut -d'|' -f2)

echo "[parse] cover: $COVER_MAIN / $COVER_SUB"
echo "[parse] watermark: $WATERMARK"

# ---- 2. 检测音频时长，自动适配 ----
DUR=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$INPUT_AUDIO")
# 向上取整到 0.1 秒，避免 ffmpeg 帧计算误差
DUR_CEIL=$(python -c "import math; print(f'{math.ceil($DUR * 10) / 10:.2f}')")
echo "[audio] duration=${DUR}s (ceil=${DUR_CEIL}s)"

# ---- 3. 生成 BGM（自适应时长） ----
BGM_FILE="bgm_$(echo $INPUT_AUDIO | sed 's/voiceover_//;s/.mp3//').mp3"
if [ ! -f "$BGM_FILE" ]; then
  ffmpeg -y -f lavfi -i "sine=frequency=110:duration=${DUR_CEIL},volume=0.06" \
    -f lavfi -i "sine=frequency=220:duration=${DUR_CEIL},volume=0.04" \
    -f lavfi -i "sine=frequency=330:duration=${DUR_CEIL},volume=0.025" \
    -f lavfi -i "sine=frequency=440:duration=${DUR_CEIL},volume=0.015" \
    -filter_complex "[0:a][1:a][2:a][3:a]amix=inputs=4:duration=first[mix]; \
[mix]aecho=0.8:0.85:300:0.4,tremolo=f=0.3:d=0.3,volume=1.5[out]" \
    -map "[out]" -c:a libmp3lame -b:a 128k "$BGM_FILE" 2>/dev/null
  echo "[bgm] generated $BGM_FILE"
fi

# ---- 4. ASCII 视觉层 ----
ASCII_FILE="ascii_$(echo $INPUT_AUDIO | sed 's/voiceover_//;s/.mp3//').mp4"
python ascii_audio_layer.py "$INPUT_AUDIO" "$ASCII_FILE" 2>&1 | tail -3
echo "[ascii] generated $ASCII_FILE"

# ---- 5. 渐变背景（自适应时长） ----
BG_FILE="bg_$(echo $INPUT_AUDIO | sed 's/voiceover_//;s/.mp3//').mp4"
ffmpeg -y -f lavfi -i "color=c=0x0a0a14:s=${W}x${H}:d=${DUR_CEIL}:r=${FPS}" \
  -vf "geq=\
r='0+30*(X/W)+5*random(0)':\
g='10+20*(X/W)+5*random(0)':\
b='20+50*(X/W)+5*random(0)',\
vignette=PI/4" \
  -c:v libx264 -pix_fmt yuv420p -preset veryfast "$BG_FILE" 2>/dev/null
echo "[bg] generated $BG_FILE"

# ---- 6. 拼装 drawtext（自适应时长） ----
DRAWTEXT=""
DRAWTEXT+="drawtext=fontfile='${FONT}':text='${COVER_MAIN}':fontcolor=white:fontsize=78:x=(w-text_w)/2:y=380:enable=between(t\,0.0\,${DUR_CEIL}),"
DRAWTEXT+="drawtext=fontfile='${FONT}':text='${COVER_SUB}':fontcolor=0x9ad8ff:fontsize=42:x=(w-text_w)/2:y=500:enable=between(t\,0.0\,${DUR_CEIL}),"

while IFS='|' read -r KEY TEXT T1 T2; do
  case "$KEY" in
    SENTENCE_*)
      SIZE=42
      [ ${#TEXT} -lt 10 ] && SIZE=54
      DRAWTEXT+="drawtext=fontfile='${FONT}':text='${TEXT}':fontcolor=white:fontsize=${SIZE}:bordercolor=black:borderw=3:x=(w-text_w)/2:y=720:enable=between(t\,${T1}\,${T2}),"
      ;;
  esac
done < <(grep '^SENTENCE_' script.txt)

DRAWTEXT+="drawtext=fontfile='${FONT}':text='${WATERMARK}':fontcolor=0x666666:fontsize=22:x=(w-text_w)/2:y=1200:enable=between(t\,0.0\,${DUR_CEIL})"

# ---- 7. 合成最终视频 ----
ffmpeg -y \
  -i "$BG_FILE" \
  -i "$ASCII_FILE" \
  -i "$INPUT_AUDIO" \
  -i "$BGM_FILE" \
  -filter_complex "\
[1:v]scale=${W}:${H},fps=${FPS}[ascii];\
[0:v][ascii]overlay=0:0:format=auto[v_bg];\
[v_bg]${DRAWTEXT}[v];\
[2:a][3:a]amix=inputs=2:duration=first:dropout_transition=0[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -pix_fmt yuv420p -preset veryfast \
  -c:a aac -b:a 128k -shortest \
  "$OUTPUT_VIDEO" 2>&1 | tail -3

echo ""
echo "=== 完成 ==="
ls -la "$OUTPUT_VIDEO"