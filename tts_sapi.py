"""
tts_sapi.py - 用 Windows SAPI 离线生成中文语音
用法: python tts_sapi.py "文本内容" output.mp3
"""
import sys
import win32com.client
import os
import subprocess
import tempfile

def tts_wav(text, wav_path):
    """用 SAPI 合成 WAV"""
    speaker = win32com.client.Dispatch("SAPI.SpVoice")
    # 找中文语音
    try:
        voices = speaker.GetVoices()
        zh_voice = None
        for i in range(voices.Count):
            v = voices.Item(i)
            desc = v.GetDescription()
            if "Chinese" in desc or "中文" in desc or "Mandarin" in desc:
                zh_voice = v
                break
        if zh_voice:
            speaker.Voice = zh_voice
            print(f"[voice] {zh_voice.GetDescription()}")
    except Exception as e:
        print(f"[voice] fallback: {e}")

    speaker.Rate = -1  # 稍慢（-10..10, 0=正常）
    speaker.Volume = 100

    # 流式写入 wav
    fs = win32com.client.Dispatch("SAPI.SpFileStream")
    fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
    fmt.Type = 22  # 16kHz 16-bit mono
    fs.Format = fmt
    fs.Open(wav_path, 3, False)  # 3 = SSFMCreateForWrite
    speaker.AudioOutputStream = fs
    speaker.Speak(text)
    fs.Close()
    speaker.AudioOutputStream = None

def wav_to_mp3(wav_path, mp3_path):
    """ffmpeg 转 wav → mp3"""
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-c:a", "libmp3lame", "-b:a", "128k", mp3_path],
        capture_output=True, check=True,
    )

if __name__ == "__main__":
    text = sys.argv[1]
    mp3_path = sys.argv[2]
    wav_tmp = tempfile.mktemp(suffix=".wav")
    print(f"[tts] {text[:50]}...")
    tts_wav(text, wav_tmp)
    wav_to_mp3(wav_tmp, mp3_path)
    os.unlink(wav_tmp)
    print(f"[done] {mp3_path}")