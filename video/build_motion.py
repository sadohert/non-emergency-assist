"""Render the two animated sections (opening and privacy diagram) as 1080p30 video, timed to the narration.

Reads word timings from video/edit2/words.json (made with ElevenLabs speech-to-text) and clip
lengths from video/narration/. Writes v01-motion.mp4, v05-motion.mp4 and motion.json (where each
narration clip starts inside its video) to video/edit2/.

Run with: uv run --with pillow python video/build_motion.py
"""
import json
import math
import pathlib
import subprocess

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1920, 1080, 30
BG = (12, 20, 17)
PANEL = (18, 28, 24)
WHITE = (246, 245, 240)
GREY = (160, 166, 156)
DIM = (64, 74, 68)
BLUE = (74, 138, 214)
TEAL = (224, 83, 63)      # coral accent: emphasis
GREEN = (47, 158, 84)     # reassuring states
MUTE = (127, 132, 123)
V = pathlib.Path("video")
OUT = V / "edit3"
WORDS = json.loads((OUT / "words.json").read_text())


def dur(p):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(p)]))


def font(size, bold=False):
    return ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", size, index=1 if bold else 0)


def clamp(x):
    return max(0.0, min(1.0, x))


def ease(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def prog(t, start, length=0.5):
    """0 before start, easing to 1 over length seconds."""
    return ease((t - start) / length)


def mix(color, alpha, base=BG):
    a = clamp(alpha)
    return tuple(round(base[i] + (color[i] - base[i]) * a) for i in range(3))


def word_time(clip, word, nth=0):
    hits = [s for w, s, _ in WORDS[clip]["words"] if w.strip(".,?:;!").lower() == word.lower()]
    return hits[nth]


def text(d, xy, s, size, color, bold=False, anchor="la"):
    d.text(xy, s, font=font(size, bold), fill=color, anchor=anchor)


def box(d, x, y, w, h, title, sub, alpha=1.0, outline=GREY, width=3, fill=PANEL, title_color=WHITE, sub_color=GREY, dashed=False):
    if alpha <= 0.01:
        return
    if dashed:
        for i in range(x, x + w, 28):
            d.line([i, y, min(i + 14, x + w), y], fill=mix(outline, alpha), width=2)
            d.line([i, y + h, min(i + 14, x + w), y + h], fill=mix(outline, alpha), width=2)
        for j in range(y, y + h, 28):
            d.line([x, j, x, min(j + 14, y + h)], fill=mix(outline, alpha), width=2)
            d.line([x + w, j, x + w, min(j + 14, y + h)], fill=mix(outline, alpha), width=2)
    else:
        d.rounded_rectangle([x, y, x + w, y + h], 18, fill=mix(fill, alpha), outline=mix(outline, alpha), width=width)
    text(d, (x + w / 2, y + h / 2 - 22), title, 36, mix(title_color, alpha), True, "mm")
    text(d, (x + w / 2, y + h / 2 + 26), sub, 25, mix(sub_color, alpha), False, "mm")


def pill(d, cx, cy, s, size, fill, color, alpha=1.0, pad=22):
    if alpha <= 0.01:
        return
    w = d.textlength(s, font=font(size, True)) + pad * 2
    h = size + 26
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], h / 2, fill=mix(fill, alpha))
    text(d, (cx, cy), s, size, mix(color, alpha, mix(fill, alpha)), True, "mm")


def arrow_h(d, x1, x2, y, color, alpha=1.0, width=4):
    """Horizontal arrow from x1 to x2 at height y."""
    if alpha <= 0.01:
        return
    c = mix(color, alpha)
    s = 1 if x2 > x1 else -1
    d.line([x1, y, x2 - s * 12, y], fill=c, width=width)
    d.polygon([(x2, y), (x2 - s * 18, y - 10), (x2 - s * 18, y + 10)], fill=c)


def arrow_v(d, x, y1, y2, color, alpha=1.0, width=4):
    if alpha <= 0.01:
        return
    c = mix(color, alpha)
    s = 1 if y2 > y1 else -1
    d.line([x, y1, x, y2 - s * 12], fill=c, width=width)
    d.polygon([(x, y2), (x - 10, y2 - s * 18), (x + 10, y2 - s * 18)], fill=c)


def elbow(d, pts, color, alpha=1.0, width=4):
    """Polyline through pts, ending in a horizontal arrowhead."""
    if alpha <= 0.01:
        return
    c = mix(color, alpha)
    d.line(pts[:-1] + [pts[-2]], fill=c, width=width, joint="curve")
    arrow_h(d, pts[-2][0], pts[-1][0], pts[-1][1], color, alpha, width)


def along(pts, p):
    """Point a fraction p of the way along a polyline."""
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lens = [math.dist(a, b) for a, b in segs]
    target = clamp(p) * sum(lens)
    for (a, b), ln in zip(segs, lens):
        if target <= ln:
            f = target / ln if ln else 0
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        target -= ln
    return pts[-1]


def spaced(d, cx, cy, s, size, color, spacing=2.0, bold=False):
    """Centred text with letter-spacing, as on the Amber Alert cards.

    Every letter is drawn on one shared baseline at a whole-pixel position. Anchoring each letter
    by its own middle made the capitals sit at slightly different heights.
    """
    f = font(size, bold)
    w = sum(d.textlength(ch, font=f) + spacing for ch in s) - spacing
    top, bottom = f.getbbox("H", anchor="ls")[1], f.getbbox("H", anchor="ls")[3]
    baseline = round(cy - (top + bottom) / 2)
    x = cx - w / 2
    for ch in s:
        d.text((round(x), baseline), ch, font=f, fill=color, anchor="ls")
        x += d.textlength(ch, font=f) + spacing
    return w


def badge(d, cx, cy, s, alpha, size=26):
    """Outlined pill with letter-spaced capitals, like the '3 SERVICES · 1 CHANNEL' badge."""
    if alpha <= 0.01:
        return
    f = font(size, True)
    w = sum(d.textlength(ch, font=f) + 2.5 for ch in s) + 56
    d.rounded_rectangle([cx - w / 2, cy - 32, cx + w / 2, cy + 32], 32, outline=mix(TEAL, alpha), width=3)
    spaced(d, cx, cy, s, size, mix(WHITE, alpha), 2.5, True)


_LOGOS = {}


def logo_chip(d, cx, cy, path, alpha):
    """An unmodified logo on an off-white chip."""
    if alpha <= 0.01:
        return
    if path not in _LOGOS:
        _LOGOS[path] = Image.open(path).convert("RGBA")
    logo = _LOGOS[path]
    w, h = logo.width + 56, 64
    d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 32, fill=mix(WHITE, alpha))
    if alpha > 0.6:
        d._image.paste(logo, (round(cx - logo.width / 2), round(cy - logo.height / 2)), logo)


def divider(d, cx, cy, alpha=1.0):
    d.line([cx - 80, cy, cx + 80, cy], fill=mix((120, 52, 42), alpha), width=2)
    d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=mix(TEAL, alpha))


def rings(d, cx, cy, alpha=1.0):
    for r, c in ((520, (14, 23, 19)), (380, (15, 25, 21)), (250, (16, 27, 22))):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=mix(c, alpha), width=3)


DISCLAIMER = "INDEPENDENT DEMONSTRATION  ·  NOT AFFILIATED WITH OR ENDORSED BY THE TORONTO POLICE SERVICE OR ELEVENLABS"


def render(name, seconds, draw_frame):
    out = OUT / f"{name}.mp4"
    proc = subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE)
    for f in range(round(seconds * FPS)):
        img = Image.new("RGB", (W, H), BG)
        draw_frame(ImageDraw.Draw(img), f / FPS)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    return out


# ---------------------------------------------------------------- section 1: opening

N = V / "narration"
GAP1 = 0.45
A0 = 0.3
B0 = A0 + dur(N / "01a-problem.mp3") + GAP1
C0 = B0 + dur(N / "01b-built.mp3") + GAP1
END1 = C0 + dur(N / "01c-knowledge.mp3") + 0.7

T_HOW = A0 + word_time("01a-problem", "How")
T_WHERE = A0 + word_time("01a-problem", "Where")
T_ELEVEN = B0 + word_time("01b-built", "ElevenLabs")
T_CLAUDE = B0 + word_time("01b-built", "Claude")
T_SEVENTEEN = C0 + word_time("01c-knowledge", "seventeen")
T_ONLINE = C0 + word_time("01c-knowledge", "online")
T_COLLISION = C0 + word_time("01c-knowledge", "collision")
T_RECORD = C0 + word_time("01c-knowledge", "record")
T_TOLD = C0 + word_time("01c-knowledge", "told")

PAGES = ["Online reporting", "Collision reporting", "Police record checks", "Non-emergency contact", "911 emergency",
         "Make the right call", "Lost property or ID", "Fraud", "Bicycle safety and theft", "Damage to vehicle under $5,000",
         "Property identification", "Records release", "Freedom of information", "Community crisis service",
         "Toronto at your service 311", "Contact", "Services overview"]
SPOKEN = {"Online reporting": T_ONLINE, "Collision reporting": T_COLLISION, "Police record checks": T_RECORD}


def bubble(d, x, y, s, size, t, start, bright=True):
    p = prog(t, start, 0.45)
    if p <= 0.01:
        return
    w = d.textlength(s, font=font(size, True)) + 64
    h = size + 52
    yy = y + (1 - p) * 34
    fill = WHITE if bright else (26, 38, 33)
    color = BG if bright else GREY
    d.rounded_rectangle([x, yy, x + w, yy + h], 28, fill=mix(fill, p))
    d.polygon([(x + 46, yy + h - 2), (x + 86, yy + h - 2), (x + 40, yy + h + 30)], fill=mix(fill, p))
    text(d, (x + 32, yy + h / 2), s, size, mix(color, p, mix(fill, p)), True, "lm")


def scene1(d, t):
    # --- A: the busy line
    fade_a = 1 - prog(t, B0 - 0.45, 0.4)
    if fade_a > 0.01:
        cx, cy = 430, 450
        for k in range(3):
            ph = ((t / 1.6) + k / 3) % 1
            r = 70 + ph * 190
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=mix(TEAL, (1 - ph) * 0.7 * fade_a), width=4)
        d.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], fill=mix(TEAL, fade_a))
        d.rounded_rectangle([cx - 22, cy - 38, cx + 22, cy + 38], 9, outline=mix(BG, fade_a, mix(TEAL, fade_a)), width=5)
        d.line([cx - 7, cy + 26, cx + 7, cy + 26], fill=mix(BG, fade_a, mix(TEAL, fade_a)), width=4)
        text(d, (cx, cy + 290), "Non-emergency line", 46, mix(WHITE, fade_a), True, "mm")
        waiting = 3 + int(clamp((t - A0) / (B0 - A0)) * 14)
        text(d, (cx, cy + 350), f"Calls waiting: {waiting}", 32, mix(GREY, fade_a), False, "mm")
        if fade_a > 0.99:
            bubble(d, 1180, 150, "Can I report this online?", 30, t, A0 + 1.6, False)
            bubble(d, 900, 760, "I lost my wallet", 30, t, A0 + 2.5, False)
            bubble(d, 1330, 830, "Minor collision, what now?", 30, t, A0 + 3.4, False)
            bubble(d, 860, 320, "How do I report a stolen bike?", 48, t, T_HOW - 0.15)
            bubble(d, 980, 520, "Where do I get a record check?", 48, t, T_WHERE - 0.15)

    # --- B: what was built
    in_b = prog(t, B0 - 0.05, 0.5) * (1 - prog(t, C0 - 0.45, 0.4))
    if in_b > 0.01:
        rings(d, W / 2, 470, in_b)
        text(d, (W / 2, 330), "Non-Emergency Assist", 112, mix(WHITE, in_b), True, "mm")
        text(d, (W / 2, 440), "A voice agent for routine police non-emergency questions", 42, mix(GREY, in_b), False, "mm")
        badge(d, 500, 600, "ELEVENLABS ELEVENAGENTS", in_b * prog(t, T_ELEVEN - 0.1))
        logo_chip(d, 960, 600, "video/logos/python.png", in_b * prog(t, T_ELEVEN + 0.5))
        badge(d, 1440, 600, "CLAUDE CODE  ·  CODING ASSISTANT", in_b * prog(t, T_CLAUDE - 0.1))
        divider(d, W / 2, 740, in_b)
        spaced(d, W / 2, 930, "NARRATION: AN ELEVENLABS CLONE OF MY OWN VOICE", 22, mix(MUTE, in_b))
        spaced(d, W / 2, 1000, DISCLAIMER, 22, mix(MUTE, in_b))

    # --- C: what the agent knows
    in_c = prog(t, C0 - 0.05, 0.5)
    if in_c > 0.01:
        text(d, (110, 90), "What the agent knows", 64, mix(WHITE, in_c), True)
        text(d, (110, 172), "Public pages from the Toronto Police website", 34, mix(GREY, in_c))
        arrived = 0
        for i, title in enumerate(PAGES):
            col, row = i % 3, i // 3
            x, y = 110 + col * 366, 260 + row * 96
            p = prog(t, T_SEVENTEEN - 0.2 + i * 0.13, 0.5)
            if p > 0.5:
                arrived += 1
            hot = title in SPOKEN and t >= SPOKEN[title] - 0.1
            glow = prog(t, SPOKEN[title] - 0.1, 0.3) if title in SPOKEN else 0
            xx = x - (1 - p) * 160
            d.rounded_rectangle([xx, y, xx + 350, y + 78], 14, fill=mix(PANEL, p * in_c),
                                outline=mix(TEAL if hot else DIM, p * in_c), width=4 if hot else 2)
            d.rectangle([xx + 16, y + 22, xx + 22, y + 56], fill=mix(TEAL if hot else BLUE, p * in_c))
            text(d, (xx + 38, y + 39), title, 22, mix(WHITE if hot or glow else (200, 208, 222), p * in_c, mix(PANEL, p * in_c)),
                 bool(hot), "lm")
        kb = prog(t, T_SEVENTEEN - 0.3, 0.6) * in_c
        d.rounded_rectangle([1290, 300, 1810, 760], 26, fill=mix(PANEL, kb), outline=mix(BLUE, kb), width=4)
        text(d, (1550, 370), "Agent knowledge base", 38, mix(WHITE, kb, mix(PANEL, kb)), True, "mm")
        text(d, (1550, 520), str(arrived), 190, mix(TEAL, kb, mix(PANEL, kb)), True, "mm")
        text(d, (1550, 680), "public pages", 38, mix(GREY, kb, mix(PANEL, kb)), False, "mm")
        arrow_h(d, 1222, 1282, 530, GREY, kb)
        told = prog(t, T_TOLD - 0.15, 0.5) * in_c
        if told > 0.01:
            d.rounded_rectangle([110, 880, 1810, 980], 22, fill=mix((16, 46, 30), told), outline=mix(GREEN, told), width=3)
            text(d, (W / 2, 930), "Answers only from these pages, and says which one.", 44, mix(WHITE, told, mix((16, 46, 30), told)), True, "mm")


# ---------------------------------------------------------------- section 5: privacy diagram

CLIPS5 = ["05a-privacy", "05b-public-knowledge", "05c-callback-fields", "05d-zero-retention", "05e-residency", "05f-own-model"]
GAP5 = 0.6
S = []
_t = 0.4
for c in CLIPS5:
    S.append(_t)
    _t += dur(N / f"{c}.mp3") + GAP5
END5 = _t + 0.8
CAPTIONS = ["What this design gives you to work with", "Knowledge: public web pages only", "A callback sends three details",
            "Zero retention mode", "Regional data residency", "Your own model, for anything sensitive"]
EL = (360, 210, 1090, 900)      # ElevenLabs panel
YS = (1190, 210, 1860, 900)     # your side panel
VOICE = (400, 300, 650, 130)
MODEL = (400, 470, 650, 130)
KB = (400, 640, 650, 130)
CBS = (1230, 300, 590, 130)
CHAN = (1230, 470, 590, 130)
OWN = (1230, 640, 590, 130)
PATH = [(1050, 535), (1140, 535), (1140, 365), (1230, 365)]


def scene5(d, t):
    step = max(i for i in range(6) if t >= S[i] - 0.25) if t >= S[0] - 0.25 else 0
    base = prog(t, 0.0, 0.6)
    text(d, (W / 2, 62), "Designing for privacy", 58, mix(WHITE, base), True, "mm")
    cap = prog(t, S[step] - 0.25, 0.4)
    text(d, (W / 2, 138), CAPTIONS[step], 38, mix(TEAL, cap), False, "mm")

    # panels
    d.rounded_rectangle(EL, 28, outline=mix(BLUE, base * 0.9), width=4)
    text(d, (EL[0] + 34, EL[1] + 22), "ElevenLabs", 34, mix(BLUE, base), True)
    d.rounded_rectangle(YS, 28, outline=mix(GREEN, base * 0.9), width=4)
    text(d, (YS[0] + 34, YS[1] + 22), "Your side", 34, mix(GREEN, base), True)

    # caller
    a = prog(t, 0.2, 0.6)
    d.ellipse([140, 300, 240, 400], outline=mix(WHITE, a), width=5)
    d.ellipse([172, 322, 208, 358], fill=mix(WHITE, a))
    d.chord([158, 362, 222, 430], 180, 360, fill=mix(WHITE, a))
    text(d, (190, 440), "Caller", 34, mix(WHITE, a), True, "mm")
    arrow_h(d, 262, 396, 365, GREY, a)

    moved = prog(t, S[5] + 0.5, 1.2)            # step f: the model moves to your side
    step_b = prog(t, S[1], 0.5)
    step_c = prog(t, S[2], 0.5)

    box(d, *VOICE, "Voice", "speech only" if moved > 0.6 else "speech in, speech out", prog(t, 0.35, 0.6),
        outline=GREEN if moved > 0.6 else GREY, width=5 if moved > 0.6 else 3, sub_color=GREEN if moved > 0.6 else GREY)
    box(d, *KB, "Knowledge base", "17 public Toronto Police pages", prog(t, 0.65, 0.6),
        outline=GREEN if step == 1 else GREY, width=6 if step == 1 else 3, sub_color=GREEN if step == 1 else GREY)
    box(d, *CBS, "Callback service", "checks, validates, cleans", prog(t, 0.8, 0.6),
        outline=TEAL if step == 2 else GREY, width=6 if step == 2 else 3)
    box(d, *CHAN, "Team channel", "Mattermost, on your network", prog(t, 0.95, 0.6),
        outline=TEAL if step == 2 else GREY, width=6 if step == 2 else 3)
    arrow_v(d, CBS[0] + CBS[2] // 2, CBS[1] + CBS[3], CHAN[1], GREY, prog(t, 1.1, 0.6))

    # the model box: starts inside ElevenLabs, moves in step f
    mx = MODEL[0] + (OWN[0] - MODEL[0]) * moved
    my = MODEL[1] + (OWN[1] - MODEL[1]) * moved
    mw = MODEL[2] + (OWN[2] - MODEL[2]) * moved
    if moved > 0.02:
        box(d, *MODEL, "", "", 0.5, outline=DIM, dashed=True)
    else:
        box(d, *OWN, "Your own model", "optional", prog(t, 1.2, 0.6) * 0.55, outline=DIM, dashed=True, title_color=GREY)
    box(d, round(mx), round(my), round(mw), MODEL[3], "Your own model" if moved > 0.6 else "Agent model",
        "hosted by you" if moved > 0.6 else "follows the prompt, decides what to say", prog(t, 0.5, 0.6),
        outline=GREEN if step == 5 else GREY, width=6 if step == 5 else 3, sub_color=GREEN if moved > 0.6 else GREY)

    # connectors
    if moved < 0.5:
        elbow(d, PATH, TEAL if step == 2 else GREY, prog(t, 1.0, 0.6) * (1 - moved * 2))
    else:
        elbow(d, [(1050, 365), (1140, 365), (1140, 705), (1230, 705)], GREEN, (moved - 0.5) * 2)

    # step b: public pages feed the knowledge base
    if step_b > 0.01:
        for k in range(3):
            x, y = 118 + k * 16, 640 + k * 14
            d.rounded_rectangle([x, y, x + 110, y + 96], 8, fill=mix(WHITE, step_b), outline=mix(DIM, step_b), width=2)
            for ln in range(4):
                d.line([x + 14, y + 20 + ln * 16, x + 96 - (ln % 2) * 22, y + 20 + ln * 16], fill=mix(GREY, step_b, mix(WHITE, step_b)), width=4)
        text(d, (190, 800), "Public web pages", 28, mix(WHITE, step_b), True, "mm")
        text(d, (190, 838), "nothing confidential", 24, mix(GREEN, step_b), False, "mm")
        arrow_h(d, 282, 396, 705, GREEN, step_b)

    # step c: three details travel to your side, then stay listed
    fields = ["first name", "phone number", "one-line summary"]
    if step_c > 0.01:
        for k, label in enumerate(fields):
            p = clamp((t - (S[2] + 0.5 + k * 0.75)) / 1.1)
            if 0 < p < 1 and moved < 0.5:
                x, y = along(PATH, ease(p))
                pill(d, x, y - 34, label, 24, WHITE, BG, 1.0, 16)
            settled = prog(t, S[2] + 0.5 + k * 0.75 + 1.0, 0.4)
            pill(d, (1305, 1478, 1702)[k], 840, label, 22, (26, 70, 44), WHITE, settled, 14)
        text(d, (1230, 790), "What arrives:", 24, mix(GREY, prog(t, S[2] + 1.4, 0.4)), False, "lm")

    # step d and e: controls on the ElevenLabs side
    pill(d, 900, 240, "Zero retention mode", 28, GREEN, BG, prog(t, S[3] + 0.1, 0.5))
    text(d, (900, 282), "limits what is kept from each call", 22, mix(GREY, prog(t, S[3] + 0.5, 0.5)), False, "mm")
    e = prog(t, S[4] + 0.1, 0.5)
    if e > 0.01:
        d.rounded_rectangle([400, 800, 1050, 870], 35, fill=mix((18, 38, 66), e), outline=mix(BLUE, e), width=3)
        d.ellipse([428, 821, 456, 849], fill=mix(BLUE, e))
        text(d, (474, 835), "Regional data residency, where it's offered", 25, mix(WHITE, e, mix((18, 38, 66), e)), True, "lm")

    spaced(d, W / 2, 1010, DISCLAIMER, 20, mix(DIM, base))


# ---------------------------------------------------------------- section 6: close

CARD2 = 4.4                       # second card starts; the closing narration starts just after
N6 = CARD2 + 0.5
END6 = N6 + dur(N / "06-close.mp3") + 2.2


def scene6(d, t):
    one = prog(t, 0.2, 0.7) * (1 - prog(t, CARD2 - 0.6, 0.5))
    two = prog(t, CARD2, 0.6)
    rings(d, W / 2, 520, max(one, two))
    if one > 0.01:
        text(d, (W / 2, 420), "Seventeen public pages. Fifteen tests.", 58, mix(WHITE, one), False, "mm")
        text(d, (W / 2, 494), "One unscripted question.", 58, mix(WHITE, one), False, "mm")
        spaced(d, W / 2, 590, "A voice agent you have to listen to, not just read.", 34, mix(TEAL, one))
        divider(d, W / 2, 668, one)
    if two > 0.01:
        spaced(d, W / 2, 330, "Built by Stu Doherty", 44, mix(TEAL, two))
        text(d, (W / 2, 396), "with Claude Code as coding assistant", 32, mix(WHITE, two), False, "mm")
        divider(d, W / 2, 470, two)
        text(d, (W / 2, 560), "Code and a one-page write-up", 50, mix(WHITE, two), False, "mm")
        text(d, (W / 2, 632), "Link in the description", 40, mix(TEAL, two), True, "mm")
    spaced(d, W / 2, 1000, DISCLAIMER, 22, mix(MUTE, max(one, two)))


def stills():
    out = V / "sample-amber"
    out.mkdir(exist_ok=True)
    shots = [("1-opening-questions", scene1, T_WHERE + 0.9), ("2-opening-title", scene1, T_CLAUDE + 1.2),
             ("3-opening-knowledge", scene1, END1 - 0.2), ("4-privacy-callback", scene5, S[2] + 4.0),
             ("5-privacy-retention", scene5, S[4] - 0.3), ("6-privacy-final", scene5, END5 - 0.2),
             ("7-close-card-1", scene6, 2.5), ("8-close-card-2", scene6, END6 - 0.5)]
    for old in out.glob("*.png"):
        old.unlink()
    for name, fn, t in shots:
        img = Image.new("RGB", (W, H), BG)
        fn(ImageDraw.Draw(img), t)
        img.save(out / f"{name}.png")
    print("stills written to", out)


if __name__ == "__main__":
    import sys
    if "--stills" in sys.argv:
        stills()
        sys.exit(0)
    render("v01-motion", END1, scene1)
    render("v05-motion", END5, scene5)
    render("v06-close-motion", END6, scene6)
    motion = {
        "v01-motion.mp4": [["01a-problem", A0], ["01b-built", B0], ["01c-knowledge", C0]],
        "v05-motion.mp4": [[c, S[i]] for i, c in enumerate(CLIPS5)],
        "v06-close-motion.mp4": [["06-close", N6]],
    }
    (OUT / "motion.json").write_text(json.dumps(motion, indent=1))
    print(f"v01-motion {END1:.1f}s, v05-motion {END5:.1f}s")
    for name, when in (("v01-motion", [A0 + 1.0, T_WHERE + 0.8, T_CLAUDE + 1.0, T_RECORD + 0.3, END1 - 0.3]),
                       ("v05-motion", [S[1] - 0.5, S[2] - 0.4, S[3] - 0.5, S[5] - 0.4, END5 - 0.3])):
        for i, ts in enumerate(when):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{ts:.2f}", "-i", str(OUT / f"{name}.mp4"),
                            "-frames:v", "1", "-vf", "scale=960:-1", str(OUT / f"check-{name}-{i}.jpg")], check=True)
