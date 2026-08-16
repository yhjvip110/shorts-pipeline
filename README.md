# Shorts Pipeline — 中文短视频自动生成流水线

把一段文案变成可发布的抖音/小红书竖屏短视频（720×1280）。

**端到端**：TTS 配音 → Whisper 自动对齐字幕 → 音频反应式 ASCII 视觉层 → 渐变背景 → drawtext 烧字幕 → 合成出片。

**全程本地**：ffmpeg + Python + faster-whisper，零云端 API 调用。

**已验证**：Windows 10 + ffmpeg 8.x + Python 3.11 + faster-whisper 1.2.1，跑通 5 条不同主题短视频，时长 16-24 秒。

---

## 效果预览

每条视频包含 5 层：

| 层 | 内容 |
|---|---|
| **封面大字** | 顶部主标题 + 副标题（贯穿全程） |
| **字幕** | 中文 SENTENCE 段，按 Whisper 自动对齐的时间区间显示 |
| **ASCII 视觉层** | 音频反应式波形 + 脉冲环 + 底部字符流 |
| **背景** | ffmpeg 渐变 + 噪点 + vignette |
| **BGM** | 4 频 sine + echo + tremolo（占位，可换 Suno/AI 生成） |

---

## 安装

### 1. 系统依赖

| 工具 | 安装方式 |
|---|---|
| **ffmpeg** | `choco install ffmpeg` 或 [官网下载](https://ffmpeg.org/) |
| **Python 3.11+** | [python.org](https://www.python.org/downloads/) |
| **simhei.ttf**（中文字体） | Windows 自带 `C:/Windows/Fonts/simhei.ttf`，其他系统装 `sudo apt install fonts-wqy-zenhei` 之类 |

### 2. Python 依赖

```bash
pip install -r requirements.txt
```

需要：`faster-whisper`, `scipy`, `numpy`, `pillow`, `pywin32`（仅 Windows TTS）

### 3. Whisper 模型（首次运行自动下载）

需要走国内镜像，否则 HuggingFace SSL 失败：

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1
```

---

## 使用

### 单条视频

#### 1. 写文案

编辑 `script.txt`：

```
COVER_MAIN|别再收藏 AI 教程了
COVER_SUB|收藏不等于会用
WATERMARK|@你的AI笔记
SENTENCE_1|我猜你手机里，至少收藏了几十条 AI 教程。|0.0|0.0
SENTENCE_2|但你真正用过的，有几条？|0.0|0.0
SENTENCE_3|收藏的瞬间，我们以为自己在学习。|0.0|0.0
SENTENCE_4|但收藏，从来不等于掌握。|0.0|0.0
SENTENCE_5|所以今天，挑一条，立刻用起来。|0.0|0.0
```

**注意**：时间填 `0.0|0.0` 占位即可，下一步会自动填充。

#### 2. 生成 TTS 音频

**选项 A**：Windows 离线（最稳定）

```bash
python tts_sapi.py "我猜你手机里，至少收藏了几十条 AI 教程。但你真正用过的，有几条？收藏的瞬间，我们以为自己在学习。但收藏，从来不等于掌握。所以今天，挑一条，立刻用起来。" voiceover.mp3
```

**选项 B**：调用 Hermes `text_to_speech` 工具（高质量，但偶发失败）

```python
text_to_speech(text="...", speed=0.85, output_path="voiceover.mp3")
```

#### 3. Whisper 自动对齐字幕

```bash
HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_XET=1 \
  python align_subtitles.py voiceover.mp3 script.txt
```

输出会覆盖 `script.txt` 里所有 `SENTENCE_N` 行的时间戳（精度 < 0.1s）。

#### 4. 合成视频

```bash
bash make_short.sh voiceover.mp3 final.mp4
```

---

### 矩阵化（多条主题）

编辑 `batch.sh` 里的 `TOPICS` 数组，每条主题一行：

```bash
declare -a TOPICS=(
  "voiceover_t1.mp3|别再收藏 AI 教程了|收藏不等于会用|文案1|0.0|3.0|...|"
  "voiceover_t2.mp3|时间不是不够|是你的注意力不够|...|"
  ...
)
```

然后：

```bash
bash batch.sh
```

会自动跑：TTS → Whisper 对齐 → 合成 → 输出 `final_t*.mp4`

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `make_short.sh` | 单条流水线（自适应时长） |
| `batch.sh` | 矩阵化批处理（5 条主题示例） |
| `tts_sapi.py` | Windows SAPI 离线 TTS（fallback） |
| `align_subtitles.py` | faster-whisper 自动填字幕时间 |
| `ascii_audio_layer.py` | 音频反应式 ASCII 视觉生成 |
| `script.txt` | 文案模板（封面 + 字幕） |
| `requirements.txt` | Python 依赖 |

---

## 已知的坑

| 现象 | 原因 | 解法 |
|---|---|---|
| TTS 返回空 | edge TTS 在 >90 字或某些内容上失败 | 用 `tts_sapi.py` |
| ffmpeg 报路径错 | MSYS bash 翻译 `/c/...` | 用 `C\\:/Windows/...` 写死 |
| drawtext 不显示 | `between(t,0,5)` 里的逗号被吃 | 写 `between(t\,0\,5)` |
| 字幕卡住不切换 | 时间填错或音频切静音 | 重跑 `align_subtitles.py` |
| ffmpeg 渲染慢（3-4 分钟/条） | `geq` 滤镜是 per-pixel | 等，或换静态背景图 |
| Whisper 报 SSL 错 | HuggingFace 直连失败 | 设 `HF_ENDPOINT=https://hf-mirror.com` |
| Whisper 模型下载走 xet 失败 | HF 新协议 | 设 `HF_HUB_DISABLE_XET=1` |

---

## TTS 选择

| Provider | 质量 | 稳定性 | 速度 | 依赖 |
|---|---|---|---|---|
| **Windows SAPI Huihui** | ⭐⭐ 机械 | ⭐⭐⭐⭐⭐ 离线 | ⭐⭐⭐ 即时 | pywin32 |
| **edge TTS** (Hermes) | ⭐⭐⭐⭐ 较自然 | ⭐⭐⭐ 偶发失败 | ⭐⭐⭐ 即时 | 网络 |
| **Suno / ElevenLabs** | ⭐⭐⭐⭐⭐ 真人级 | ⭐⭐⭐⭐ API | ⭐⭐ 10s/条 | API key |

**本仓库默认走 SAPI**（零依赖、零失败）。要更好声音：换 `make_short.sh` 里调 TTS 的步骤用 edge 或 Suno。

---

## BGM 说明

当前 BGM 是**合成占位音**（4 频 sine + echo + tremolo），听起来像 80 年代电子游戏。

要真 AI BGM：
1. 用 [Suno](https://suno.com/) 出 30 秒原创
2. 把 mp3 文件放到 `bgm_*.mp3`
3. 改 `make_short.sh` 第 47-51 行，直接用你的 mp3 而不是 sine

---

## License

MIT — 随便用，注明出处即可。

---

## 致谢

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — Whisper CTranslate2 重实现
- [ascii-video skill](https://github.com) — 启发 ASCII 视觉层设计
- 验证用环境：Windows 10 + ffmpeg 8.1 + Python 3.11