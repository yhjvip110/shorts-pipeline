#!/usr/bin/env bash
# batch.sh - 矩阵化批处理多条主题短视频
#
# 用法: bash batch.sh
# 前置: 改下面的 TOPICS 数组定义每条主题
#       每条格式: "voiceover_xxx.mp3|封面大字|封面副标|句1|起|止|句2|起|止|..."
# 输出: final_xxx.mp4（每条一条）
#
# 流水线: 改 script.txt → Whisper 自动对齐字幕 → 调 make_short.sh 合成

set -e
cd "$(dirname "$0")"

# ---- 主题定义 ----
# 格式: 音频文件|封面大字|封面副标|字幕1|起|止|字幕2|起|止|...
declare -a TOPICS=(
  "voiceover_t1.mp3|别再收藏 AI 教程了|收藏不等于会用|我猜你手机里，至少收藏了几十条 AI 教程。|0.0|4.0|但你真正用过的，有几条？|4.5|7.0|收藏的瞬间，我们以为自己在学习。|7.5|11.0|但收藏，从来不等于掌握。|11.5|15.5|所以今天，挑一条，立刻用起来。|16.0|20.0"
  "voiceover_t2.mp3|时间不是不够|是你的注意力不够|总说时间不够用，但你刷手机，三小时一晃就没了。|0.0|4.0|不是时间太少，是注意力被切走了。|4.5|7.5|时间管理没用，你得管注意力。|8.0|11.5|关掉推送，专注两小时，你会发现，世界不一样。|12.0|16.0"
  "voiceover_t3.mp3|不是执行力差|是任务不够具体|为什么你的执行力差？|0.0|3.0|不是你懒，是任务不够具体。|3.5|6.0|说要运动的人，永远不会动。|6.5|9.0|说今天跑三公里的人，可能真的会出门。|9.5|13.5|模糊带来焦虑，具体带来行动。|14.0|17.0"
  "voiceover_t4.mp3|复利的真相很残酷|大多数人会中途下车|复利不是慢慢变富。|0.0|3.0|复利的真相很残酷，是大多数人中途下车。|3.5|7.5|能坚持十年的人，不是意志力强。|8.0|11.5|是把坚持，变成了习惯。|12.0|15.0"
  "voiceover_t5.mp3|你不需要更多选择|你需要更少决策|你不需要更多时间。|0.0|3.0|你需要更少选择。|3.5|6.0|选项越多，决策越累，行动越少。|6.5|9.5|所以高手的方法是，提前定好规则。|10.0|13.5|减少临场决策，让行动自动化。|14.0|17.0"
)

WATERMARK="@你的AI笔记"

# ---- 写通用 script.txt（覆盖主题文案用单独的临时文件） ----
for i in "${!TOPICS[@]}"; do
  TOPIC="${TOPICS[$i]}"
  IDX=$((i + 1))
  AUDIO=$(echo "$TOPIC" | cut -d'|' -f1)
  MAIN=$(echo "$TOPIC" | cut -d'|' -f2)
  SUB=$(echo "$TOPIC" | cut -d'|' -f3)
  OUTPUT="final_t${IDX}.mp4"

  echo ""
  echo "===== Theme $IDX: $MAIN / $SUB ====="

  # 生成临时 script.txt
  TMP_SCRIPT="_script_t${IDX}.txt"
  cat > "$TMP_SCRIPT" <<EOF
COVER_MAIN|$MAIN
COVER_SUB|$SUB
WATERMARK|$WATERMARK
EOF
  # 解析剩余字段为 SENTENCE 行
  REST=$(echo "$TOPIC" | cut -d'|' -f4-)
  SENT_IDX=1
  while [ -n "$REST" ]; do
    TEXT=$(echo "$REST" | cut -d'|' -f1)
    T1=$(echo "$REST" | cut -d'|' -f2)
    T2=$(echo "$REST" | cut -d'|' -f3)
    echo "SENTENCE_${SENT_IDX}|${TEXT}|${T1}|${T2}" >> "$TMP_SCRIPT"
    REST=$(echo "$REST" | cut -d'|' -f4-)
    SENT_IDX=$((SENT_IDX + 1))
  done

  # 替换 script.txt
  cp script.txt "script.txt.bak"
  cp "$TMP_SCRIPT" script.txt

  # Whisper 自动对齐字幕时间（仅 SENTENCE 行的时间被覆盖）
  echo "[align] running whisper alignment..."
  HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
    python align_subtitles.py "$AUDIO" script.txt 2>&1 | tail -7

  # 跑流水线
  bash make_short.sh "$AUDIO" "$OUTPUT"

  # 还原
  mv "script.txt.bak" script.txt
  rm "$TMP_SCRIPT"

  echo "[done] $OUTPUT"
done

echo ""
echo "===== 全部完成 ====="
ls -la final_t*.mp4 2>/dev/null