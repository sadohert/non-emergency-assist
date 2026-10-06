"""Build the rough-cut assets in video/edit2/ and anchors.json (which audio clip goes with which video segment).

Video segments are 1920x1080, 30 fps, silent, with black bars where the recording is narrower than 16:9.
Audio is 48 kHz mono WAV, loudness-levelled. Run video/build_motion.py first for the two animated sections.
Run with: uv run python video/build_edit_assets.py
"""
import json, subprocess, pathlib

V = pathlib.Path("video"); E = V / "edit3"; E.mkdir(exist_ok=True)
N = V / "narration"; X = V / "calls/excerpts"

def run(*a): subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, a)], check=True)
def dur(p): return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)]))
SCALE = "scale=-2:1080:flags=lanczos,pad=1920:1080:(ow-iw)/2:0:black,fps=30,format=yuv420p"
def vseg(name, src, a, b):
    out = E / f"{name}.mp4"
    run("-ss", a, "-to", b, "-i", V / src, "-an", "-vf", SCALE, "-c:v", "libx264", "-crf", "17", "-preset", "medium", out); return out.name
def lufs(p):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(p), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return float(err.split("Integrated loudness:")[1].split("I:")[1].split("LUFS")[0])
def aseg(name, src, a=None, b=None, mute_first=0.0):
    """Cut to 48 kHz mono, then set loudness with a fixed gain and limiter so the length never changes.
    Narration is levelled to -16 LUFS and call audio to -19, so the narration leads."""
    out = E / f"{name}.wav"; raw = E / f"_raw_{name}.wav"; args = [] if a is None else ["-ss", a, "-to", b]
    run(*args, "-i", src, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", raw)
    gain = (-19 if name.startswith("x-") else -16) - lufs(raw)
    mute = f"volume=enable='lt(t,{mute_first})':volume=0," if mute_first else ""
    run("-i", raw, "-af", f"{mute}volume={gain:.2f}dB,alimiter=limit=0.84:attack=3:release=60:level=disabled",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", out)
    raw.unlink(); return out.name
motion = json.loads((E / "motion.json").read_text())
video, anchors = [], []      # anchors: (audio file, track, video file, offset seconds)
def seg(v, audio=None, track=1, offset=0.0):
    video.append(v)
    if audio: anchors.append((audio, track, v, offset))

# 1. animated opening
seg("v01-motion.mp4")
for clip, at in motion["v01-motion.mp4"]: anchors.append((aseg(f"n{clip}", N / f"{clip}.mp3"), 1, "v01-motion.mp4", at))
# 2. live call (scene_01 = call time + 2.87)
n2 = N / "02-live-call.mp3"; G = 0.35
a1, a2, a3 = aseg("n02-1", n2, 0, 4.40), aseg("n02-2", n2, 4.40, 11.55), aseg("n02-3", n2, 11.55, 18.89)
seg(vseg("v02-1-narr", "scene_01.mov", 10.4, 10.4 + 4.40 + G), a1)
seg(vseg("v02-2-call-opening", "scene_01.mov", 15.6, 23.1 + G), aseg("x-call1-A", X / "call1-A-opening.wav"), 2)
seg(vseg("v02-3-narr", "scene_01.mov", 28.0, 28.0 + 7.15 + G), a2)
seg(vseg("v02-4-call-guidance", "scene_01.mov", 37.6, 50.8 + G), aseg("x-call1-B", X / "call1-B-guidance.wav"), 2)
seg(vseg("v02-5-narr", "scene_01.mov", 78.0, 78.0 + 7.34 + G), a3)
seg(vseg("v02-6-call-readback", "scene_01.mov", 94.1, 105.6), aseg("x-call1-C1", X / "call1-C1-readback.wav"), 2)
seg(vseg("v02-7-call-reference", "scene_01.mov", 108.7, 121.6), aseg("x-call1-C2", X / "call1-C2-reference.wav"), 2)
# 3. safety (scene_02 = call time + 2.54); the narration starts over the end of the Mattermost shot
seg(vseg("v03-1-narr", "scene_02.mov", 0.0, 8.9), aseg("n03-safety", N / "03-safety.mp3"), 1, -1.25)
seg(vseg("v03-2-call-escalation", "scene_02.mov", 9.0, 21.3), aseg("x-call2", X / "call2-escalation.wav", mute_first=0.42), 2)
# 4. how it's built
s2 = dur(V / "scene_03_shot_02.mov")
seg(vseg("v04a-yaml", "scene_03_shot_01.mov", 14.0, 23.0), aseg("n04-how-its-built", N / "04-how-its-built.mp3"), 1, 0.3)
seg(vseg("v04b-command", "scene_03_shot_02.mov", 0.5, 4.5))
seg(vseg("v04c-results", "scene_03_shot_02.mov", s2 - 9.5, s2 - 0.3))
# 5. animated privacy diagram
seg("v05-motion.mp4")
for clip, at in motion["v05-motion.mp4"]: anchors.append((aseg(f"n{clip}", N / f"{clip}.mp3"), 1, "v05-motion.mp4", at))
# 6. animated close: a summary card, then the credit card with the closing line
seg("v06-close-motion.mp4")
for clip, at in motion["v06-close-motion.mp4"]: anchors.append((aseg(f"n{clip}", N / f"{clip}.mp3"), 1, "v06-close-motion.mp4", at))

(E / "anchors.json").write_text(json.dumps({"video": video, "anchors": anchors,
    "frames": {a: round(dur(E / a) * 30) for a, *_ in anchors}}, indent=1))
print(len(video), "video segments;", len(anchors), "audio clips")
