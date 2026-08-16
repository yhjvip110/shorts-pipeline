"""
ascii_audio_layer.py - Audio-reactive ASCII visual layer for short video.

Reads an audio file, computes per-frame FFT bands, renders ASCII characters
onto 720x1280 frames using those band energies, pipes to ffmpeg.

Output: an .mp4 video file (no audio, h264 yuv420p) — meant to be overlaid
onto a video as the audio-reactive layer.

Usage:
    python ascii_audio_layer.py [input.mp3] [output.mp4]

Defaults: voiceover_full.mp3 → ascii_layer.mp4
"""
import subprocess, tempfile, wave, math, os, sys
import numpy as np
from scipy.fft import rfft, rfftfreq
from PIL import Image, ImageDraw, ImageFont

# ---------- Config (CLI args override defaults) ----------
if len(sys.argv) >= 2:
    AUDIO_IN = sys.argv[1]
else:
    AUDIO_IN = "voiceover_full.mp3"

if len(sys.argv) >= 3:
    OUT_VIDEO = sys.argv[2]
else:
    OUT_VIDEO = "ascii_layer.mp4"

W, H       = 720, 1280
FPS        = 24
FONT_PATH  = r"C:\Windows\Fonts\consola.ttf"
FONT_SIZE  = 10
COLS       = W // (FONT_SIZE // 2 + 4)   # character grid width
ROWS       = H // (FONT_SIZE + 2)        # character grid height
PAL        = " .,:;+*?%$#@"
MAX_BRIGHT = 200.0

# ---------- Step 1: decode audio to mono 22050Hz wav ----------
tmp_wav = tempfile.mktemp(suffix=".wav")
subprocess.run(
    ["ffmpeg", "-y", "-i", AUDIO_IN, "-ac", "1", "-ar", "22050", "-sample_fmt", "s16", tmp_wav],
    capture_output=True, check=True,
)
with wave.open(tmp_wav) as wf:
    sr = wf.getframerate()
    raw = wf.readframes(wf.getnframes())
samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
hop = sr // FPS
n_frames = len(samples) // hop
duration = n_frames / FPS

print(f"[audio] sr={sr}  total_samples={len(samples)}  frames={n_frames}  dur={duration:.2f}s")

# ---------- Step 2: per-frame band energies ----------
win = hop * 2
window = np.hanning(win)
freqs = rfftfreq(win, 1.0 / sr)

def band_energy(chunk, lo, hi):
    spec = np.abs(rfft(chunk * window))
    fmask = (freqs >= lo) & (freqs < hi)
    return float(np.sqrt(np.mean(spec[fmask] ** 2)) + 1e-9)

# Band definitions (sub/bass/mid/hi)
def features_for(chunk):
    return [
        band_energy(chunk, 20,   120),    # sub
        band_energy(chunk, 120,  500),    # bass
        band_energy(chunk, 500,  2000),   # mid
        band_energy(chunk, 2000, 8000),   # hi
    ]

def features_for_safe(idx):
    start = idx * hop
    chunk = samples[start:start + win]
    if len(chunk) < win:
        chunk = np.pad(chunk, (0, win - len(chunk)))
    return features_for(chunk)
raw_feats = np.array([features_for_safe(i) for i in range(n_frames)])
# Normalize per band to 0..1
feats = raw_feats / (raw_feats.max(axis=0) + 1e-9)
print(f"[feats] shape={feats.shape}  per-band max={raw_feats.max(axis=0)}")

# ---------- Step 3: render frames → ffmpeg pipe ----------
font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
char_w, char_h = font.getbbox("M")[2], font.getbbox("M")[3] + 2
GRID_W = W // char_w
GRID_H = H // char_h

print(f"[grid] {GRID_W}x{GRID_H} cells, char={char_w}x{char_h}px")

def render_frame(t, band):
    """band = normalized [sub, bass, mid, hi]"""
    img = Image.new("RGB", (W, H), (8, 10, 22))
    draw = ImageDraw.Draw(img)

    # Background tint reacts to bass
    b_bass = float(band[1])
    bg_r = int(8 + 20 * b_bass)
    bg_g = int(10 + 10 * b_bass)
    bg_b = int(22 + 60 * b_bass)
    draw.rectangle([0, 0, W, H], fill=(bg_r, bg_g, bg_b))

    # Waveform line: horizontal sine whose amplitude = mid band
    mid = float(band[2])
    hi  = float(band[3])
    sub = float(band[0])

    n_pts = 240
    cy = H // 2
    amp = 80 + 220 * mid
    pts = []
    for i in range(n_pts):
        x = int(i * (W - 1) / (n_pts - 1))
        # layered sine
        y = cy + int(amp * math.sin(i * 0.1 + t * 3) *
                      (0.6 + 0.4 * math.sin(i * 0.05 + t * 2)))
        pts.append((x, y))
    # Draw wave (thicker)
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i+1]], fill=(200, 230, 255), width=3)

    # Sub-bass: pulse rings from center
    for k in range(4):
        radius = int((1 - sub) * (k + 1) * 80 + 20)
        if radius > 4:
            r = int(80 + 175 * (1 - sub) * (4 - k) / 4)
            g = int(120 + 100 * mid)
            b = int(200 + 55 * hi)
            draw.ellipse([W//2 - radius, cy - radius//3, W//2 + radius, cy + radius//3],
                         outline=(r, g, b), width=2)

    # (Removed: top-left SUB/BASS/MID/HI/T technical text overlay — was visual noise)

    # ASCII character stream along the bottom — character palette driven by hi band
    pal_idx = int(hi * (len(PAL) - 1))
    row_y = H - 80
    line = ""
    import random
    rng = random.Random(int(t * 100))
    for c in range(GRID_W):
        # Choose char based on mixed feature
        mix = 0.5 * mid + 0.5 * hi
        idx = int(mix * (len(PAL) - 1) + rng.random() * 0.3)
        idx = max(0, min(len(PAL) - 1, idx))
        line += PAL[idx]
    draw.text((20, row_y), line, fill=(220, 200, 255), font=font)

    return img

# Build ffmpeg pipe
cmd = [
    "ffmpeg", "-y",
    "-f", "rawvideo",
    "-vcodec", "rawvideo",
    "-s", f"{W}x{H}",
    "-pix_fmt", "rgb24",
    "-r", str(FPS),
    "-i", "-",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-preset", "veryfast",
    OUT_VIDEO
]
proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

for fi in range(n_frames):
    band = feats[fi]
    t = fi / FPS
    img = render_frame(t, band)
    proc.stdin.write(img.tobytes())

proc.stdin.close()
proc.wait()
print(f"[done] {OUT_VIDEO}  frames={n_frames}  dur={duration:.2f}s")
os.unlink(tmp_wav)