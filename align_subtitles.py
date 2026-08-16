"""
align_subtitles.py - 用 faster-whisper 给音频自动转写，
                    然后把转写结果和 script.txt 里的 SENTENCE 文案做模糊匹配，
                    自动填充起始/结束时间。

用法: python align_subtitles.py <audio.mp3> <script.txt>
输出: 修改后的 script.txt（覆盖原文件）
"""
import sys
import subprocess
import tempfile
import wave
import os
import re
from difflib import SequenceMatcher

def normalize_text(s):
    """去标点 + 空格 + 转小写，便于模糊匹配"""
    s = re.sub(r'[，。！？、；：""''《》（）()\[\]【】,.!?;:"\'`~\-—]', '', s)
    s = re.sub(r'\s+', '', s)
    return s

def transcribe_with_word_timestamps(audio_path):
    """
    用 faster-whisper 转写音频，返回 [(word, start, end), ...] 列表
    """
    from faster_whisper import WhisperModel

    # tiny/int8: 速度优先，适合 10-30s 短视频
    print("[whisper] loading model (tiny, int8)...")
    model = WhisperModel("tiny", device="cpu", compute_type="int8")

    print(f"[whisper] transcribing {audio_path}...")
    segments, info = model.transcribe(
        audio_path,
        language="zh",
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 200},
    )

    words = []
    for seg in segments:
        if seg.words:
            for w in seg.words:
                words.append((w.word.strip(), w.start, w.end))

    print(f"[whisper] language={info.language}  segments={len(words)}")
    return words

def align_subtitles(words, sentences):
    """
    把音频转写出的连续文本和 script.txt 的每句话做模糊匹配。
    返回 [(sentence_text, start_time, end_time), ...]
    """
    # 拼出连续字符串 + 索引→时间映射
    concatenated = ""
    char_to_word_idx = []  # 每个字符对应的 word index
    word_idx_to_time = []  # 每个 word 的 (start, end)
    for wi, (w, s, e) in enumerate(words):
        concatenated += w
        char_to_word_idx.extend([wi] * len(w))
        word_idx_to_time.append((s, e))

    # normalize 后保留位置映射
    norm_concat = normalize_text(concatenated)
    norm_orig_chars = []  # (original_index_in_concat, char)
    for i, ch in enumerate(concatenated):
        if re.match(r'[一-鿿]', ch) or ch.isalnum():
            norm_orig_chars.append((i, ch))
    norm_concat_clean = ''.join(c for _, c in norm_orig_chars)

    results = []
    cursor = 0  # 在 norm_concat_clean 中的位置

    for sent in sentences:
        norm_sent = normalize_text(sent)
        if not norm_sent:
            continue

        # 在剩余文本里找最相似的连续子串
        # 用 SequenceMatcher 找最匹配的子序列
        matcher = SequenceMatcher(None, norm_concat_clean[cursor:], norm_sent, autojunk=False)
        match = matcher.find_longest_match(0, len(norm_concat_clean) - cursor, 0, len(norm_sent))

        if match.size == 0:
            print(f"[align] WARN: no match for: {sent}")
            results.append((sent, None, None))
            continue

        start_in_norm = cursor + match.a
        end_in_norm = cursor + match.a + match.size

        # norm chars → original concat chars
        if start_in_norm < len(norm_orig_chars) and end_in_norm <= len(norm_orig_chars):
            start_orig_idx = norm_orig_chars[start_in_norm][0]
            end_orig_idx = norm_orig_chars[end_in_norm - 1][0] if end_in_norm > 0 else start_orig_idx
        else:
            print(f"[align] WARN: index out of range for: {sent}")
            results.append((sent, None, None))
            cursor = end_in_norm
            continue

        # 找到起始 word idx（向前看，扩展到包含该 word 起始的字符）
        start_word_idx = char_to_word_idx[start_orig_idx] if start_orig_idx < len(char_to_word_idx) else 0
        end_word_idx = char_to_word_idx[end_orig_idx] if end_orig_idx < len(char_to_word_idx) else len(words) - 1

        t_start, _ = word_idx_to_time[start_word_idx]
        _, t_end = word_idx_to_time[end_word_idx]

        # 句末延后 0.1s（让字幕结束时间比词末稍晚一点）
        t_end = min(t_end + 0.15, t_start + 4.0)  # 单句不超过 4s

        results.append((sent, t_start, t_end))
        print(f"[align] {sent[:30]}...  {t_start:.2f}s - {t_end:.2f}s")
        cursor = end_in_norm

    return results

def update_script_file(script_path, alignments):
    """把对齐结果写回 script.txt 的 SENTENCE 行"""
    with open(script_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    sent_idx = 0
    for line in lines:
        m = re.match(r'^(SENTENCE_\d+)\|(.+?)\|([\d.]+)\|([\d.]+)\s*$', line)
        if m and sent_idx < len(alignments):
            key, text, _, _ = m.groups()
            _, t1, t2 = alignments[sent_idx]
            if t1 is not None and t2 is not None:
                new_lines.append(f"{key}|{text}|{t1:.2f}|{t2:.2f}\n")
                sent_idx += 1
                continue
        new_lines.append(line)

    with open(script_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f"[update] wrote {sent_idx} aligned SENTENCE rows to {script_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python align_subtitles.py <audio.mp3> <script.txt>")
        sys.exit(1)

    audio_path = sys.argv[1]
    script_path = sys.argv[2]

    # 解析 script.txt 里的 SENTENCE 文案
    sentences = []
    with open(script_path, 'r', encoding='utf-8') as f:
        for line in f:
            m = re.match(r'^SENTENCE_\d+\|(.+?)\|[\d.]+\|[\d.]+\s*$', line)
            if m:
                sentences.append(m.group(1))

    print(f"[script] {len(sentences)} sentences to align")

    # 1. 转写
    words = transcribe_with_word_timestamps(audio_path)
    if not words:
        print("[error] no words transcribed")
        sys.exit(1)

    # 2. 对齐
    alignments = align_subtitles(words, sentences)

    # 3. 写回 script.txt
    update_script_file(script_path, alignments)

    # 输出对齐结果
    print("\n=== 对齐结果 ===")
    for text, t1, t2 in alignments:
        if t1 is not None:
            print(f"  {t1:.2f}-{t2:.2f}s: {text}")
        else:
            print(f"  ???: {text}")