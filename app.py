"""EditAI Studio - single-file AI video editing app (cloud/phone deployment)."""
import os, re, json, time, uuid, threading, logging, subprocess, math
from pathlib import Path

"""Editing presets, platform targets and style templates for EditAI Studio."""

PLATFORMS = {
    "instagram_reels": {"label": "Instagram Reels", "aspect": "9:16",  "target_duration": 30,  "max_duration": 90},
    "youtube_shorts":  {"label": "YouTube Shorts",  "aspect": "9:16",  "target_duration": 30,  "max_duration": 60},
    "tiktok":          {"label": "TikTok",          "aspect": "9:16",  "target_duration": 25,  "max_duration": 60},
    "youtube":         {"label": "YouTube Video",   "aspect": "16:9",  "target_duration": 180, "max_duration": 600},
    "square":          {"label": "Square / Feed",   "aspect": "1:1",   "target_duration": 30,  "max_duration": 120},
    "promo":           {"label": "Website Promo",   "aspect": "16:9",  "target_duration": 45,  "max_duration": 120},
}

# Each style preset maps to real FFmpeg filter chains + editing behavior.
STYLE_PRESETS = {
    "cinematic": {
        "label": "Cinematic Film",
        "grade": "eq=contrast=1.12:saturation=0.88:brightness=-0.02,curves=blue='0/0 0.5/0.45 1/0.9':red='0/0 0.5/0.52 1/1.02',vignette=PI/5",
        "transition": "fade", "transition_duration": 0.5,
        "segment_target": 3.5, "speed_ramps": True, "slowmo": True,
        "caption_style": "lower-third", "music_mood": "epic orchestral",
        "letterbox": True,
    },
    "vibrant": {
        "label": "Vibrant / Hype",
        "grade": "eq=contrast=1.08:saturation=1.35:brightness=0.01,unsharp=5:5:0.6",
        "transition": "zoompan", "transition_duration": 0.35,
        "segment_target": 2.2, "speed_ramps": True, "slowmo": False,
        "caption_style": "bold-pop", "music_mood": "upbeat pop",
        "letterbox": False,
    },
    "noir": {
        "label": "Noir / Moody",
        "grade": "hue=s=0,eq=contrast=1.25:brightness=-0.04,noise=alls=6:allf=t",
        "transition": "fadeblack", "transition_duration": 0.6,
        "segment_target": 4.0, "speed_ramps": False, "slowmo": False,
        "caption_style": "minimal", "music_mood": "dark ambient",
        "letterbox": True,
    },
    "warm_travel": {
        "label": "Warm Travel",
        "grade": "colortemperature=temperature=5800,eq=contrast=1.05:saturation=1.15:brightness=0.02,curves=red='0/0 0.5/0.56 1/0.98'",
        "transition": "fade", "transition_duration": 0.5,
        "segment_target": 3.0, "speed_ramps": True, "slowmo": True,
        "caption_style": "lower-third", "music_mood": "chill acoustic",
        "letterbox": False,
    },
    "cool_tech": {
        "label": "Cool / Tech",
        "grade": "colortemperature=temperature=7200,eq=contrast=1.1:saturation=0.95,curves=blue='0/0.02 0.5/0.58 1/1.06'",
        "transition": "wipeleft", "transition_duration": 0.4,
        "segment_target": 2.6, "speed_ramps": True, "slowmo": False,
        "caption_style": "minimal", "music_mood": "synthwave electronic",
        "letterbox": False,
    },
    "gaming": {
        "label": "Gaming / Montage",
        "grade": "eq=contrast=1.15:saturation=1.25,unsharp=7:7:0.8",
        "transition": "glitch", "transition_duration": 0.25,
        "segment_target": 1.8, "speed_ramps": True, "slowmo": True,
        "caption_style": "bold-pop", "music_mood": "phonk / heavy beat",
        "letterbox": False,
    },
    "clean": {
        "label": "Clean / Corporate",
        "grade": "eq=contrast=1.03:saturation=1.05",
        "transition": "fade", "transition_duration": 0.4,
        "segment_target": 4.0, "speed_ramps": False, "slowmo": False,
        "caption_style": "minimal", "music_mood": "light corporate",
        "letterbox": False,
    },
}

PROMPT_KEYWORDS = {
    "platforms": {
        "instagram reels": "instagram_reels", "ig reels": "instagram_reels", "reels": "instagram_reels",
        "youtube shorts": "youtube_shorts", "shorts": "youtube_shorts",
        "tiktok": "tiktok",
        "youtube video": "youtube", "youtube": "youtube", "long form": "youtube",
        "square": "square", "1:1": "square", "feed post": "square",
        "promo": "promo", "website promo": "promo", "ad": "promo", "advertisement": "promo",
    },
    "styles": {
        "cinematic": "cinematic", "film look": "cinematic", "movie": "cinematic",
        "vibrant": "vibrant", "hype": "vibrant", "colorful": "vibrant",
        "noir": "noir", "moody": "noir", "black and white": "noir", "b&w": "noir",
        "travel": "warm_travel", "warm": "warm_travel", "golden": "warm_travel",
        "tech": "cool_tech", "cool": "cool_tech", "futuristic": "cool_tech",
        "gaming": "gaming", "montage": "gaming", "gameplay": "gaming",
        "car": "cinematic", "cars": "cinematic", "automotive": "cinematic",
        "fashion": "vibrant", "model": "vibrant",
        "corporate": "clean", "clean": "clean", "minimal": "clean", "professional": "clean",
    },
    "transitions": {
        "whip": "wipeleft", "glitch": "glitch", "zoom": "zoompan", "zoom transition": "zoompan",
        "fade": "fade", "dissolve": "fade", "light leak": "fade", "smooth": "fade",
        "no transitions": "none", "hard cut": "none", "jump cut": "none",
    },
    "grades": {
        "teal and orange": "eq=contrast=1.1,curves=blue='0/0.04 0.5/0.55 1/1.05':red='0/0 0.5/0.54 1/1.03'",
        "warm": STYLE_PRESETS["warm_travel"]["grade"],
        "cool": STYLE_PRESETS["cool_tech"]["grade"],
        "black and white": "hue=s=0,eq=contrast=1.15",
        "vintage": "curves=r='0/0.05 0.5/0.5 1/0.95':g='0/0.03 0.5/0.48 1/0.9':b='0/0.1 0.5/0.42 1/0.8',noise=alls=4:allf=t",
        "fade": "curves=all='0/0.06 0.5/0.52 1/0.96',eq=saturation=0.9",
    },
}

CANVAS_SIZES = {
    "9:16":  {"1080p": (1080, 1920), "4k": (2160, 3840)},
    "16:9":  {"1080p": (1920, 1080), "4k": (3840, 2160)},
    "1:1":   {"1080p": (1080, 1080), "4k": (2160, 2160)},
}

QUALITY_PRESETS = {
    "draft":  {"crf": "28", "preset": "veryfast", "label": "Draft (fast)"},
    "high":   {"crf": "20", "preset": "medium",   "label": "High Quality"},
    "4k":     {"crf": "18", "preset": "slow",     "label": "Master 4K"},
}

# Caption style -> ASS style overrides (burned via libass)
CAPTION_STYLES = {
    "bold-pop": {
        "Fontname": "DejaVu Sans Bold", "Fontsize": 22, "PrimaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000", "Outline": 3, "Shadow": 1, "Alignment": 8, "Bold": 1,
    },
    "lower-third": {
        "Fontname": "DejaVu Sans", "Fontsize": 16, "PrimaryColour": "&H00FFFFFF",
        "OutlineColour": "&H80000000", "Outline": 1, "Shadow": 0, "Alignment": 2, "Bold": 0,
    },
    "minimal": {
        "Fontname": "DejaVu Sans", "Fontsize": 14, "PrimaryColour": "&H00F0F0F0",
        "OutlineColour": "&H00000000", "Outline": 1, "Shadow": 0, "Alignment": 2, "Bold": 0,
    },
}

MUSIC_MOODS = {
    "epic orchestral": {"tempo_bpm": 100, "tone": "cinematic"},
    "upbeat pop": {"tempo_bpm": 118, "tone": "bright"},
    "dark ambient": {"tempo_bpm": 80, "tone": "dark"},
    "chill acoustic": {"tempo_bpm": 92, "tone": "warm"},
    "synthwave electronic": {"tempo_bpm": 104, "tone": "neon"},
    "phonk / heavy beat": {"tempo_bpm": 128, "tone": "heavy"},
    "light corporate": {"tempo_bpm": 110, "tone": "clean"},
}


"""AI prompt analyzer: turns a natural-language edit request into a structured EditPlan.

Uses an LLM (OpenAI-compatible API or local Ollama) when available, otherwise a
robust keyword/grammar rule engine. Never fails: always returns a valid plan.
"""

import os
import re
import json
import logging


log = logging.getLogger("editai.analyzer")


def _llm_available():
    return bool(os.environ.get("OPENAI_API_KEY")) or bool(os.environ.get("OLLAMA_HOST"))


def _llm_analyze(prompt):
    """Ask an LLM to produce a strict JSON edit plan. Returns dict or None."""
    schema_hint = {
        "platform": "instagram_reels|youtube_shorts|tiktok|youtube|square|promo",
        "style": "|".join(STYLE_PRESETS.keys()),
        "aspect": "9:16|16:9|1:1",
        "transitions": "fade|wipeleft|glitch|zoompan|fadeblack|none",
        "speed_ramps": "bool", "slowmo": "bool", "beat_sync": "bool",
        "captions": "bool", "caption_style": "bold-pop|lower-third|minimal",
        "music_mood": "|".join(MUSIC_MOODS.keys()),
        "color_grade": "string (ffmpeg filter chain) or null",
        "target_duration_sec": "number", "tone_words": ["3-6 words describing the video"],
    }
    system = ("You are the editing planner inside a video editing app. Reply with ONLY "
              "a JSON object matching this shape: " + json.dumps(schema_hint))
    try:
        if os.environ.get("OPENAI_API_KEY"):
            from openai import OpenAI
            client = OpenAI()
            resp = client.chat.completions.create(
                model=os.environ.get("EDITAI_LLM_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}, temperature=0.2)
            return json.loads(resp.choices[0].message.content)
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        import urllib.request
        req = urllib.request.Request(
            host.rstrip("/") + "/api/generate",
            data=json.dumps({"model": os.environ.get("EDITAI_LLM_MODEL", "llama3.1"),
                             "prompt": system + "\n\nUser request: " + prompt,
                             "stream": False, "format": "json"}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(json.loads(r.read())["response"])
    except Exception as e:  # noqa: BLE001 - any LLM failure falls back to rules
        log.warning("LLM analysis failed (%s); falling back to rule engine", e)
        return None


def _rule_analyze(prompt):
    p = " " + prompt.lower() + " "
    plan = {}

    def _has(phrase):
        return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", p) is not None

    for phrase, plat in PROMPT_KEYWORDS["platforms"].items():
        if _has(phrase):
            plan["platform"] = plat
            break
    for phrase, style in PROMPT_KEYWORDS["styles"].items():
        if _has(phrase):
            plan["style"] = style
            break
    for phrase, tr in PROMPT_KEYWORDS["transitions"].items():
        if _has(phrase):
            plan["transitions"] = tr
            break
    for phrase, grade in PROMPT_KEYWORDS["grades"].items():
        if _has(phrase):
            plan["color_grade"] = grade
            break

    if "9:16" in p or "vertical" in p:
        plan["aspect"] = "9:16"
    elif "1:1" in p or "square" in p:
        plan["aspect"] = "1:1"
    elif "16:9" in p or "widescreen" in p or "landscape" in p:
        plan["aspect"] = "16:9"

    # only set keys when explicitly detected — lets preset defaults apply otherwise
    if re.search(r"speed ramp|speedramp|ramping", p):
        plan["speed_ramps"] = True
    if re.search(r"slow[ -]?mo|slow motion", p):
        plan["slowmo"] = True
    if re.search(r"beat[ -]?sync|on beat|to the beat|music sync", p):
        plan["beat_sync"] = True
    if re.search(r"caption|subtitle|text", p):
        plan["captions"] = True
    if plan["captions"] and re.search(r"bold|hype|pop", p):
        plan["caption_style"] = "bold-pop"
    elif plan["captions"] and re.search(r"minimal|clean|simple", p):
        plan["caption_style"] = "minimal"

    for mood in MUSIC_MOODS:
        if mood.split(" ")[0] in p:
            plan["music_mood"] = mood
            break

    dur = re.search(r"(\d{1,3})\s*(seconds|secs|sec|s\b)", p)
    if dur:
        plan["target_duration_sec"] = int(dur.group(1))

    # word-activation scores: which genre dominates the prompt
    scores = {}
    for style, words in {
        "cinematic": ["cinematic", "film", "movie", "epic", "dramatic"],
        "vibrant":   ["vibrant", "hype", "energetic", "colorful", "pop"],
        "gaming":    ["gaming", "gameplay", "montage", "clip", "kill"],
        "warm_travel": ["travel", "adventure", "wander", "trip", "vacation"],
        "noir":      ["noir", "moody", "dark", "mystery"],
        "clean":     ["corporate", "promo", "product", "brand", "professional"],
    }.items():
        scores[style] = sum(1 for w in words if re.search(r"\b" + w + r"\b", p))
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        plan.setdefault("style", best)
    return plan


def build_plan(prompt, media_meta=None):
    """Merge LLM/rule analysis with defaults into a complete, valid EditPlan."""
    meta = media_meta or []
    raw, engine = None, "rules"
    if _llm_available():
        raw = _llm_analyze(prompt)
        engine = "llm"
    if not raw:
        raw = _rule_analyze(prompt)
        engine = "rules"

    platform = raw.get("platform") if raw.get("platform") in PLATFORMS else None
    platform = platform or ("youtube" if any(m.get("duration", 0) > 90 for m in meta) else "instagram_reels")

    style = raw.get("style") if raw.get("style") in STYLE_PRESETS else None
    if not style:
        p = prompt.lower()
        style = ("gaming" if re.search(r"gam|montage", p) else
                 "cinematic" if re.search(r"cinemat|film|car|automotive", p) else
                 "vibrant" if re.search(r"fashion|hype|vibrant", p) else
                 "warm_travel" if re.search(r"travel|vlog|adventure", p) else
                 "clean" if platform == "promo" else "cinematic")

    preset = STYLE_PRESETS[style]
    aspect = raw.get("aspect") if raw.get("aspect") in ("9:16", "16:9", "1:1") else PLATFORMS[platform]["aspect"]
    duration = raw.get("target_duration_sec") or PLATFORMS[platform]["target_duration"]

    total_src = sum(m.get("duration", 3.0) for m in meta if m.get("type") == "video")
    total_src += 3.0 * sum(1 for m in meta if m.get("type") == "image")
    if total_src <= 0:
        total_src = float(duration)

    plan = {
        "prompt": prompt,
        "platform": platform,
        "platform_label": PLATFORMS[platform]["label"],
        "style": style,
        "style_label": preset["label"],
        "aspect": aspect,
        "target_duration": min(float(duration), PLATFORMS[platform]["max_duration"]),
        "available_source_sec": round(total_src, 1),
        "transitions": raw.get("transitions") or preset["transition"],
        "transition_duration": preset["transition_duration"],
        "speed_ramps": bool(raw.get("speed_ramps", preset["speed_ramps"])),
        "slowmo": bool(raw.get("slowmo", preset["slowmo"])),
        "beat_sync": bool(raw.get("beat_sync", True)),
        "captions": bool(raw.get("captions", True)),
        "caption_style": raw.get("caption_style") or preset["caption_style"],
        "music_mood": raw.get("music_mood") or preset["music_mood"],
        "color_grade": raw.get("color_grade") or preset["grade"],
        "letterbox": bool(preset.get("letterbox", False)),
        "segment_target": preset["segment_target"],
        "music_track": None,  # user-uploaded music wins
        "engine": engine,
    }
    return plan


def transcribe_captions(media_paths):
    """Return list of {text, start, end} using Whisper if installed, else None."""
    try:
        import whisper  # noqa
    except ImportError:
        return None
    try:
        model = whisper.load_model(os.environ.get("EDITAI_WHISPER_MODEL", "base"))
        captions = []
        offset = 0.0
        for path in media_paths:
            result = model.transcribe(path, word_timestamps=True)
            for seg in result.get("segments", []):
                captions.append({"text": seg["text"].strip(),
                                 "start": round(offset + seg["start"], 2),
                                 "end": round(offset + seg["end"], 2)})
            try:
                offset += float(probe(path).get("duration") or 0)
            except Exception:  # noqa
                offset += seg["end"] if result.get("segments") else 0
        return captions
    except Exception as e:  # noqa
        log.warning("Whisper transcription failed: %s", e)
        return None


def placeholder_captions(plan, keywords):
    """Heuristic captions when no ASR is available: hook + keyword beats."""
    dur = plan["target_duration"]
    hooks = {
        "cinematic": ["The moment you've been waiting for", None, "Every frame tells a story"],
        "vibrant":   ["Wait for it...", None, "This is the vibe"],
        "gaming":    ["INSANE play", None, "Clutch or kick?"],
        "warm_travel": ["Wander often", None, "Collect moments, not things"],
        "noir":      ["Some stories are told in shadows", None, "The city never sleeps"],
        "clean":     ["Introducing something new", None, "Built different"],
    }
    hook = hooks.get(plan["style"], hooks["cinematic"])
    caps = []
    if hook[0]:
        caps.append({"text": hook[0], "start": 0.4, "end": min(3.4, dur)})
    words = [w for w in keywords if 2 < len(w) < 18][:3]
    for i, w in enumerate(words):
        t = dur * (0.25 + 0.25 * i)
        caps.append({"text": w.upper() if plan["caption_style"] == "bold-pop" else w.title(),
                     "start": round(t, 2), "end": round(min(t + 2.5, dur - 0.3), 2)})
    if hook[2]:
        caps.append({"text": hook[2], "start": round(max(dur - 3.5, 0.5), 2), "end": round(dur - 0.4, 2)})
    return caps


"""FFmpeg-based AI editing engine for EditAI Studio.

Pipeline per render job:
  1. probe all media (ffprobe)
  2. smart-cut segmentation (scene detection / beat grid / uniform fallback)
  3. per-segment speed ramps + slow-mo (setpts/atempo, optional minterpolate)
  4. normalize every segment to the target canvas (scale/crop/pad, fps, pixel fmt)
  5. transitions via chained xfade / acrossfade (up to MAX_XFADE)
  6. global color grade (+ optional letterbox), ASS captions burn (libass)
  7. music mix with sidechain-ducked voice (sidechaincompress)
  8. encode with quality presets up to 4K
"""

import os
import re
import json
import math
import subprocess
import logging
from pathlib import Path


log = logging.getLogger("editai.engine")

FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "ffprobe")
FPS = 30
MAX_XFADE = 8           # chained xfade beyond this gets numerically unstable
XFADE_OFFSET_GUARD = 0.05

XFADE_NAMES = {"fade", "wipeleft", "wiperight", "fadeblack", "fadewhite",
               "slideleft", "slideright", "circleopen", "circleclose",
               "zoompan", "glitch"}
GLITCH_CHAIN = "noise=alls=20:allf=t,eq=contrast=1.3,rgbashift=rh=8:gh=-6:bh=4"


def _run(cmd, logfile):
    logfile.write_text("$ " + " ".join(cmd) + "\n\n", encoding="utf-8")
    with open(logfile, "a", encoding="utf-8") as f:
        proc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return proc.returncode == 0


def probe(path):
    """Return {duration, width, height, fps, has_audio, type} for a media file."""
    cmd = [FFPROBE, "-v", "error", "-show_entries",
           "format=duration:stream=codec_type,codec_name,width,height,r_frame_rate",
           "-of", "json", str(path)]
    try:
        out = json.loads(subprocess.run(cmd, capture_output=True, text=True,
                                        timeout=60).stdout)
    except Exception:  # noqa
        return {"duration": 0.0, "width": 0, "height": 0, "fps": FPS,
                "has_audio": False, "type": "video"}
    streams = out.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    try:
        num, den = (v.get("r_frame_rate") or "30/1").split("/")
        fps = float(num) / float(den or 1)
    except Exception:  # noqa
        fps = FPS
    ext = Path(path).suffix.lower()
    is_image = ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff") or \
        v.get("codec_name") in ("png", "mjpeg", "webp")
    return {
        "duration": float(out.get("format", {}).get("duration") or 0.0),
        "width": int(v.get("width") or 0), "height": int(v.get("height") or 0),
        "fps": fps or FPS, "has_audio": has_audio,
        "type": "image" if is_image else "video",
    }


# --------------------------------------------------------------------------- #
# Segmentation: smart cuts
# --------------------------------------------------------------------------- #

def detect_scene_cuts(path, threshold=0.32, limit=15):
    """Scene-detection cut points via the scdet filter."""
    cmd = [FFMPEG, "-i", str(path), "-vf",
           f"scdet=threshold={threshold}:sc_pass=1,showinfo", "-f", "null", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return []
    pts = [float(m) for m in
           re.findall(r"pts_time:([\d.]+)", p.stderr) if float(m) > 0.5]
    return pts[:limit]


def detect_beats(path, bpm_hint=120):
    """Onset-based beat grid. Uses librosa if installed, else BPM fallback."""
    try:
        import librosa  # noqa
        y, sr = librosa.load(path, sr=22050, mono=True)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, start_bpm=bpm_hint)
        times = librosa.frames_to_time(beats, sr=sr)
        return [round(float(t), 3) for t in times if t > 1.0][:24]
    except Exception:  # noqa
        info = probe(path)
        dur = info.get("duration") or 30.0
        step = 60.0 / max(bpm_hint, 60)
        return [round(i * step, 3) for i in range(1, int(dur / step))][:24]


def build_segments(media, plan, workdir, progress_cb=None):
    def prog(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)
    """Return list of segment dicts: {src, start, end, speed, slowmo}.

    Smart-cut strategy: scene cuts from the longest video source, quantized to
    the beat grid when beat_sync is on, uniform fallback otherwise.
    """
    segs = []
    target = float(plan["target_duration"])
    st = float(plan.get("segment_target", 3.0))
    want = max(3, min(14, int(target / st)))

    videos = [m for m in media if m["type"] == "video" and m.get("duration", 0) > 1]
    images = [m for m in media if m["type"] == "image"]

    if videos:
        prog(10, "Scanning video for scene changes…")
        main = max(videos, key=lambda m: m["duration"])
        cuts = detect_scene_cuts(main["path"], limit=want + 2)
        prog(45, "Scene scan done, syncing beats…")
        if plan.get("beat_sync") and main.get("has_audio"):
            beats = detect_beats(main["path"])
            if cuts and beats:
                # quantize detected scene cuts to the nearest beat
                cuts = sorted({min(beats, key=lambda b: abs(b - c)) for c in cuts})
            elif beats:
                # no scene cuts: snap a uniform cut grid to the beat
                grid = [i * main["duration"] / want for i in range(1, want)]
                cuts = sorted({min(beats, key=lambda b: abs(b - g)) for g in grid})
        bounds = [0.0] + [c for c in cuts if 0.8 < c < main["duration"] - 0.8]
        bounds = bounds[:want + 1]
        if len(bounds) < 2:
            bounds = [i * main["duration"] / want for i in range(want + 1)]
        for i in range(len(bounds) - 1):
            segs.append({"src": main["path"], "start": bounds[i],
                         "end": bounds[i + 1], "speed": 1.0, "slowmo": False})
        # B-roll: remaining videos/images spliced as short inserts
        pool = [m for m in videos if m is not main] + images
        for j, m in enumerate(pool[: max(0, want - len(segs))]):
            d = min(m.get("duration") or 2.5, st)
            segs.insert(min(1 + j * 2, len(segs)),
                        {"src": m["path"], "start": 0.0, "end": d,
                         "speed": 1.0, "slowmo": False, "image": m["type"] == "image"})
    else:
        per = target / max(len(images), 1)
        for m in images:
            segs.append({"src": m["path"], "start": 0.0,
                         "end": min(per * 1.4, 4.0), "speed": 1.0,
                         "slowmo": False, "image": True})

    prog(75, "Arranging clips on the timeline…")
    # --- pace to target duration ------------------------------------------------
    raw = sum(s["end"] - s["start"] for s in segs)
    if raw <= 0:
        raw = 1.0
    # never stretch source material beyond ~2x — trim the target instead
    if videos and target > raw * 2.0:
        target = raw * 2.0
    factor = raw / target
    for s in segs:
        s["speed"] = min(max(factor, 0.5), 2.5)
        s["duration"] = (s["end"] - s["start"]) / s["speed"]

    # --- speed ramps ------------------------------------------------------------
    if plan.get("speed_ramps") and len(segs) >= 4:
        pattern = [1.35, 1.0, 0.75, 1.6, 1.0, 0.85, 1.45, 1.0]
        for i, s in enumerate(segs):
            if s.get("image"):
                continue
            s["speed"] = min(max(s["speed"] * pattern[i % len(pattern)], 0.4), 3.0)
            s["duration"] = (s["end"] - s["start"]) / s["speed"]

    # --- slow-motion highlight --------------------------------------------------
    if plan.get("slowmo") and len(segs) >= 3:
        cands = [i for i, s in enumerate(segs) if not s.get("image")]
        if cands:
            idx = max(cands, key=lambda i: segs[i]["duration"])
            segs[idx]["speed"] *= 0.45
            segs[idx]["duration"] = (segs[idx]["end"] - segs[idx]["start"]) / segs[idx]["speed"]
            segs[idx]["slowmo"] = True

    prog(92, "Applying speed ramps & slow motion…")
    # renormalize so the timeline lands on target duration
    total = sum(s["duration"] for s in segs)
    scale = total / target if total > 0 else 1.0
    for s in segs:
        s["duration"] /= scale
        if not s.get("image"):
            s["speed"] *= scale
    return segs


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _atempo_chain(speed):
    """atempo only accepts [0.5, 2.0] -> chain for extreme values."""
    steps = []
    sp = speed
    while sp > 2.0:
        steps.append(2.0)
        sp /= 2.0
    while sp < 0.5:
        steps.append(0.5)
        sp /= 0.5
    steps.append(round(sp, 3))
    return ",".join(f"atempo={x}" for x in steps)


def _canvas_filter(w, h):
    return (f"scale=w={w}:h={h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={FPS},format=yuv420p")


def write_ass(captions, style_name, canvas_w, canvas_h, path,
              title=None, letterbox=False):
    """Render caption list to an ASS subtitle file."""
    st = CAPTION_STYLES.get(style_name, CAPTION_STYLES["lower-third"])
    def ts(t):
        t = max(0.0, float(t))
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    margin_v = 60 if letterbox else 40
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {canvas_w}",
        f"PlayResY: {canvas_h}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,{Fontname},{Fontsize},{PrimaryColour},&H000019FF,"
        "{OutlineColour},&H00000000,{Bold},0,0,0,100,100,0,0,1,{Outline},"
        "{Shadow},{Alignment},24,24,{mv},1".format(mv=margin_v, **st), "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
    ]
    if title:
        lines.append(f"Dialogue: 0,{ts(0.2)},{ts(2.4)},Default,,0,0,0,,"
                     f"{{\\an8\\b1}}{title}")
    for c in captions or []:
        text = str(c["text"]).replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{ts(c['start'])},{ts(c['end'])},Default,,0,0,0,,{text}")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def _ass_filter_path(path):
    """Escape a file path for use inside ffmpeg's subtitles filter."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


# --------------------------------------------------------------------------- #
# Render
# --------------------------------------------------------------------------- #

def render(plan, media, out_path, workdir, captions=None, music=None,
           quality="high", progress_cb=None, title=None):
    """Render the full edit. Returns (ok, message)."""
    workdir = Path(workdir); workdir.mkdir(parents=True, exist_ok=True)
    out_path = Path(out_path)
    q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["high"])
    canvas_w, canvas_h = CANVAS_SIZES[plan["aspect"]][
        "4k" if quality == "4k" else "1080p"]
    segs = plan.get("segments") or build_segments(media, plan, workdir)

    def prog(pct, msg):
        if progress_cb:
            progress_cb(pct, msg)

    # ---- pass 1: normalize every segment onto the target canvas --------------
    norm = []
    for i, s in enumerate(segs):
        prog(5 + int(55 * i / max(len(segs), 1)), f"Cutting segment {i+1}/{len(segs)}")
        src = s["src"]
        dur = float(s["duration"])
        speed = float(s.get("speed", 1.0))
        vf = _canvas_filter(canvas_w, canvas_h)
        if s.get("slowmo") and os.environ.get("EDITAI_INTERP") == "1":
            vf = f"minterpolate=fps={FPS*2}:mi_mode=blend," + vf
        vf = f"setpts=(PTS-STARTPTS)/{speed:.4f}," + vf
        seg_out = workdir / f"seg_{i:03d}.mp4"
        cmd = [FFMPEG, "-y", "-v", "error", "-stats"]
        if s.get("image"):
            cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(src)]
        else:
            cmd += ["-ss", f"{float(s['start']):.3f}",
                    "-t", f"{(float(s['end'])-float(s['start'])):.3f}", "-i", str(src)]
        if not s.get("image"):
            info = probe(src)
            if info.get("has_audio"):
                af = f"asetpts=PTS-STARTPTS,{_atempo_chain(speed)},aresample=48000," \
                     "aformat=channel_layouts=stereo,apad=whole_dur={:.3f}".format(dur)
                cmd += ["-af", af, "-shortest"]
            else:
                cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
                        "anullsrc=r=48000:cl=stereo"]
        else:
            cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i",
                    "anullsrc=r=48000:cl=stereo"]
        cmd += ["-vf", vf, "-t", f"{dur + 0.1:.3f}", "-c:v", "libx264",
                "-preset", "ultrafast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", str(seg_out)]
        if not _run(cmd, workdir / f"seg_{i:03d}.log"):
            return False, f"segment {i} normalization failed (see logs)"
        norm.append(seg_out)

    durations = [float(probe(p).get("duration") or 0.01) for p in norm]

    # ---- pass 2a: concat + transitions -> timeline intermediate --------------
    prog(65, "Compositing timeline")
    inputs, fc = [], []
    for p in norm:
        inputs += ["-i", str(p)]
    n = len(norm)
    vlabels = [f"[{i}:v]" for i in range(n)]
    alabels = [f"[{i}:a]" for i in range(n)]

    tr = plan.get("transitions", "fade")
    zoom_em = tr == "zoompan"          # xfade has no zoompan: emulate with zoompan filter
    if zoom_em:
        tr = "fade"
    use_x = tr in XFADE_NAMES and tr != "none" and 2 <= n <= MAX_XFADE + 1
    tr_d = min(float(plan.get("transition_duration", 0.4)), 1.0)

    cur_v, cur_a = vlabels[0], alabels[0]
    if use_x:
        for k in range(1, n):
            off = sum(durations[:k]) - k * tr_d
            if off < XFADE_OFFSET_GUARD:
                off = XFADE_OFFSET_GUARD
            vo = f"[vx{k}]"; ao = f"[ax{k}]"
            # "glitch" is emulated with xfade's pixelize transition
            chain = "transition=pixelize" if tr == "glitch" else f"transition={tr}"
            fc.append(f"{cur_v}{vlabels[k]}xfade={chain}:duration={tr_d:.3f}:offset={off:.3f}{vo}")
            fc.append(f"{cur_a}{alabels[k]}acrossfade=d={tr_d:.3f}{ao}")
            cur_v, cur_a = vo, ao
    else:
        fc.append("".join(vlabels) + f"concat=n={n}:v=1:a=0[vcat]")
        fc.append("".join(alabels) + f"concat=n={n}:v=0:a=1[acat]")
        cur_v, cur_a = "[vcat]", "[acat]"

    if zoom_em and n > 1:  # punch-in zoom emulation
        z = "[vpunch]"
        fc.append(f"{cur_v}zoompan=z='min(zoom+0.0015,1.12)':d=1:x='iw/2-(iw/zoom/2)':"
                  f"y='ih/2-(ih/zoom/2)':s={canvas_w}x{canvas_h}:fps={FPS}{z}")
        cur_v = z

    fc.append(f"{cur_v}format=yuv420p[vtl]")
    fc.append(f"{cur_a}aresample=48000,aformat=channel_layouts=stereo[atl]")
    timeline = workdir / "timeline.mp4"
    cmd = [FFMPEG, "-y", "-v", "error", "-stats"] + inputs + \
        ["-filter_complex", ";".join(fc), "-map", "[vtl]", "-map", "[atl]",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(timeline)]
    if not _run(cmd, workdir / "timeline.log"):
        return False, "timeline compositing failed (see timeline.log)"
    total_d = float(probe(timeline).get("duration") or sum(durations))

    # ---- pass 2b: grade, letterbox, captions, music mix, final encode ---------
    prog(80, "Color grading & captions")
    vf = "[0:v]" + (plan["color_grade"] + "," if plan.get("color_grade") else "")
    if plan.get("letterbox"):
        bar = int(canvas_h * 0.09)
        vf += f"pad={canvas_w}:{canvas_h + 2 * bar}:0:{bar}:color=black,"
    if captions:
        ass_path = workdir / "captions.ass"
        write_ass(captions, plan.get("caption_style", "lower-third"),
                  canvas_w, canvas_h, ass_path, title=title,
                  letterbox=plan.get("letterbox", False))
        vf += f"subtitles='{_ass_filter_path(ass_path)}',"
    vf += "format=yuv420p[vfinal]"

    a_inputs, af, amap = [], "[0:a]aresample=48000,aformat=channel_layouts=stereo[va0]", "[va0]"
    if music:
        prog(84, "Mixing music (AI ducking)")
        a_inputs = ["-i", str(music)]
        af += (f";[1:a]atrim=0:{total_d:.3f},asetpts=PTS-STARTPTS,aresample=48000,"
               f"aformat=channel_layouts=stereo,volume=0.32[mus]"
               f";[va0][mus]sidechaincompress=threshold=0.02:ratio=8:"
               f"attack=40:release=600:makeup=1.2[amixout]")
        amap = "[amixout]"

    prog(88, f"Encoding ({q['label']})")
    cmd = [FFMPEG, "-y", "-v", "error", "-stats", "-i", str(timeline)] + a_inputs + \
        ["-filter_complex", ";".join([vf, af]), "-map", "[vfinal]", "-map", amap,
         "-c:v", "libx264", "-preset", q["preset"], "-crf", q["crf"],
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(out_path)]
    if not _run(cmd, workdir / "render.log"):
        return False, "final encode failed (see render.log)"
    prog(100, "Done")
    return True, "ok"


"""Project persistence: save/load edit plans + media references as JSON."""

import json
import time
import uuid
from pathlib import Path


class ProjectStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, data):
        pid = data.get("id") or uuid.uuid4().hex[:12]
        data["id"] = pid
        data["updated_at"] = time.time()
        (self.root / f"{pid}.json").write_text(json.dumps(data, indent=2),
                                               encoding="utf-8")
        return pid

    def load(self, pid):
        p = self.root / f"{pid}.json"
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def list(self):
        out = []
        for f in sorted(self.root.glob("*.json"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": d.get("id"), "name": d.get("name", "Untitled"),
                        "platform": d.get("plan", {}).get("platform"),
                        "updated_at": d.get("updated_at")})
        return out


"""EditAI Studio - Flask application server.

Run:  python app.py        (requires ffmpeg + ffprobe on PATH)
"""

import os
import re
import json
import time
import uuid
import threading
import logging
import shutil
from pathlib import Path

from flask import (Flask, request, jsonify, send_from_directory, abort, Response)
from werkzeug.utils import secure_filename


logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("editai.app")

BASE = Path(__file__).parent
DATA = Path(os.environ.get("EDITAI_DATA", BASE / "data"))
UPLOADS = DATA / "uploads"
JOBS = DATA / "jobs"
PROJECTS = DATA / "projects"
for d in (UPLOADS, JOBS, PROJECTS):
    d.mkdir(parents=True, exist_ok=True)
_fh = logging.FileHandler(DATA / "app.log", encoding="utf-8")
_fh.setLevel(logging.ERROR)
logging.getLogger().addHandler(_fh)

store = ProjectStore(PROJECTS)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB
JOBS_LOCK = threading.Lock()
JOBS_STATUS = {}  # job_id -> {status, progress, message, output, error}


import traceback as _tb
from werkzeug.exceptions import HTTPException as _HTTPException

@app.errorhandler(Exception)
def _unhandled(e):
    if isinstance(e, _HTTPException):
        return e
    tb = _tb.format_exc()
    log.error("unhandled error: %s\n%s", e, tb)
    return jsonify(description=str(e), traceback=tb.splitlines()[-1]), 500

ALLOWED = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v",
           ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff",
           ".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"}


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #

@app.post("/api/upload")
def upload():
    files = request.files.getlist("files")
    if not files:
        abort(400, "no files")
    uid = uuid.uuid4().hex[:12]
    dest = UPLOADS / uid
    dest.mkdir(parents=True)
    media, music = [], []
    for f in files:
        name = secure_filename(f.filename or "file")
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED:
            continue
        p = dest / f"{uuid.uuid4().hex[:8]}{ext}"
        f.save(p)
        if ext in (".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"):
            music.append({"path": str(p), "name": name})
        else:
            info = probe(p)
            info.update({"path": str(p), "name": name, "url": f"/media/{uid}/{p.name}"})
            media.append(info)
    return jsonify({"session": uid, "media": media, "music": music})



@app.post("/api/upload_init")
def upload_init():
    body = request.get_json(force=True)
    uid = body.get("session") or ""
    if not re.fullmatch(r"[a-f0-9]{12}", uid):
        uid = uuid.uuid4().hex[:12]
    (UPLOADS / uid).mkdir(parents=True, exist_ok=True)
    return jsonify({"session": uid})

@app.post("/api/upload_chunk")
def upload_chunk():
    sid = request.form.get("session", "")
    if not re.fullmatch(r"[a-f0-9]{12}", sid):
        abort(400, "bad session")
    try:
        idx = int(request.form.get("index", "-1"))
    except ValueError:
        abort(400, "bad index")
    f = request.files.get("chunk")
    if f is None or not (0 <= idx <= 200000):
        abort(400, "bad chunk")
    dest = UPLOADS / sid
    dest.mkdir(parents=True, exist_ok=True)
    f.save(dest / f"part_{idx:06d}")
    return jsonify({"ok": True, "index": idx})

@app.post("/api/upload_commit")
def upload_commit():
    body = request.get_json(force=True)
    sid = body.get("session", "")
    name = secure_filename(body.get("name") or "file.bin")
    try:
        size = int(body.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if not re.fullmatch(r"[a-f0-9]{12}", sid):
        abort(400, "bad session")
    dest = UPLOADS / sid
    parts = sorted(dest.glob("part_*"))
    if not parts:
        abort(400, "no chunks received")
    final = dest / f"{uuid.uuid4().hex[:8]}{Path(name).suffix.lower() or '.bin'}"
    with open(final, "wb") as out:
        for p in parts:
            with open(p, "rb") as ch:
                shutil.copyfileobj(ch, out)
    for p in parts:
        p.unlink()
    actual = final.stat().st_size
    if size and actual != size:
        final.unlink()
        abort(400, f"file damaged in transfer ({actual} of {size} bytes) - please re-upload")
    info = probe(final)
    ext = final.suffix.lower()
    if ext in (".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"):
        kind = "music"
    elif info.get("width") or info.get("duration") or info.get("type") == "image":
        kind = "media"
    else:
        final.unlink()
        return jsonify({"skipped": True,
                        "reason": f"'{name}' is not a video, photo or audio file"})
    entry = dict(info, path=str(final), name=name, url=f"/media/{sid}/{final.name}")
    return jsonify({"ok": True, "kind": kind, "entry": entry, "bytes": actual})

@app.get("/media/<sid>/<name>")
def media(sid, name):
    if not re.fullmatch(r"[a-f0-9]{12}", sid) or "/" in name:
        abort(404)
    return send_from_directory(UPLOADS / sid, name)


def _session_media(session):
    d = UPLOADS / session
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir()):
        info = probe(p)
        info.update({"path": str(p), "name": p.name,
                     "url": f"/media/{session}/{p.name}"})
        out.append(info)
    return out


def _analyze_work(job_id, prompt, session, inline_media):
    def cb(pct, msg):
        with JOBS_LOCK:
            JOBS_STATUS[job_id].update(progress=pct, message=msg)
    try:
        media = _session_media(session) if session else \
            [dict(m, path=m["path"]) for m in inline_media]
        cb(5, "AI is reading your prompt…")
        plan = build_plan(prompt, media)
        caps = None
        vids = [m["path"] for m in media if m["type"] == "video"]
        if plan["captions"] and vids:
            cb(20, "Listening for speech (captions)…")
            caps = transcribe_captions(vids[:1])
        if caps is None:
            kws = [w for w in re.findall(r"[a-zA-Z]{3,}", prompt)
                   if w.lower() not in ("with", "make", "video", "edit", "that",
                                        "this", "and", "the", "for", "from")]
            caps = placeholder_captions(plan, kws)
        segs = build_segments(media, plan, JOBS / job_id,
                              progress_cb=lambda p, m: cb(30 + int(p * 0.6), m))
        plan["segments"] = [{k: (str(v) if k == "src" else v) for k, v in s.items()}
                            for s in segs]
        result = {"plan": plan, "captions": caps,
                  "presets": {k: v["label"] for k, v in STYLE_PRESETS.items()},
                  "platforms": {k: v["label"] for k, v in PLATFORMS.items()},
                  "moods": list(MUSIC_MOODS),
                  "qualities": {k: v["label"] for k, v in QUALITY_PRESETS.items()}}
        with JOBS_LOCK:
            JOBS_STATUS[job_id].update(status="done", progress=100,
                                       message="Analysis complete", result=result)
    except Exception as e:
        import traceback
        log.error("analysis crashed: %s\n%s", e, traceback.format_exc())
        with JOBS_LOCK:
            JOBS_STATUS[job_id].update(status="error",
                                       message="analysis crashed: " + str(e))


@app.post("/api/analyze")
def analyze():
    body = request.get_json(force=True)
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        abort(400, "prompt required")
    job_id = uuid.uuid4().hex[:12]
    (JOBS / job_id).mkdir(parents=True)
    with JOBS_LOCK:
        JOBS_STATUS[job_id] = {"status": "running", "progress": 0,
                               "message": "Starting", "output": None, "error": None}
    threading.Thread(target=_analyze_work,
                     args=(job_id, prompt, body.get("session"),
                           body.get("media", [])), daemon=True).start()
    return jsonify({"job": job_id})


def _do_render(job_id, plan, media_paths, music_path, captions, quality, title):
    try:
        _do_render_inner(job_id, plan, media_paths, music_path, captions, quality, title)
    except Exception as e:
        import traceback
        with JOBS_LOCK:
            JOBS_STATUS[job_id].update(status="error",
                message="render crashed: " + str(e))
        log.error("render crashed: %s\n%s", e, traceback.format_exc())

def _do_render_inner(job_id, plan, media_paths, music_path, captions, quality, title):
    def cb(pct, msg):
        with JOBS_LOCK:
            JOBS_STATUS[job_id].update(progress=pct, message=msg)
    job_dir = JOBS / job_id
    out = job_dir / "output.mp4"
    ok, msg = render(plan, media_paths, out, job_dir,
                            captions=captions, music=music_path,
                            quality=quality, progress_cb=cb, title=title)
    with JOBS_LOCK:
        st = JOBS_STATUS[job_id]
        if ok and out.exists():
            st.update(status="done", progress=100, message="Render complete",
                      output=f"/jobs/{job_id}/output.mp4")
        else:
            st.update(status="error", message=msg)


@app.post("/api/render")
def render():
    body = request.get_json(force=True)
    plan = body["plan"]
    session = body.get("session")
    media = _session_media(session) if session else []
    by_path = {m["path"]: m for m in media}

    # rebuild segment media entries (plan carries file paths as strings)
    segs, media_for_engine = [], []
    for s in plan.get("segments", []):
        src = s["src"]
        info = by_path.get(src) or probe(src)
        entry = dict(info, path=src)
        media_for_append(entry)
        segs.append(dict(s, image=entry["type"] == "image"))
    plan["segments"] = segs
    if not media_for_engine:
        media_for_engine = media

    music_path = None
    if body.get("music_path"):
        mp = Path(body["music_path"])
        if mp.exists() and str(mp).startswith(str(UPLOADS)):
            music_path = mp

    job_id = uuid.uuid4().hex[:12]
    (JOBS / job_id).mkdir(parents=True)
    with JOBS_LOCK:
        JOBS_STATUS[job_id] = {"status": "running", "progress": 0,
                               "message": "Starting", "output": None, "error": None}
    t = threading.Thread(target=_do_render,
                         args=(job_id, plan, media_for_engine, music_path,
                               body.get("captions"), body.get("quality", "high"),
                               body.get("title")),
                         daemon=True)
    t.start()
    return jsonify({"job": job_id})


@app.get("/api/job/<job_id>")
def job(job_id):
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        abort(404)
    with JOBS_LOCK:
        st = dict(JOBS_STATUS.get(job_id) or {})
    if not st:
        abort(404)
    return jsonify(st)


@app.get("/jobs/<job_id>/output.mp4")
def job_output(job_id):
    if not re.fullmatch(r"[a-f0-9]{12}", job_id):
        abort(404)
    p = JOBS / job_id / "output.mp4"
    if not p.exists():
        abort(404)
    return send_from_directory(JOBS / job_id, "output.mp4",
                               mimetype="video/mp4")


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #

@app.post("/api/project/save")
def project_save():
    body = request.get_json(force=True)
    pid = store.save(body)
    return jsonify({"id": pid})


@app.get("/api/project/<pid>")
def project_load(pid):
    d = store.load(pid)
    if not d:
        abort(404)
    return jsonify(d)


@app.get("/api/projects")
def project_list():
    return jsonify(store.list())


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #

@app.get("/api/meta")
def meta():
    return jsonify({
        "platforms": {k: v["label"] for k, v in PLATFORMS.items()},
        "presets": {k: v["label"] for k, v in STYLE_PRESETS.items()},
        "qualities": {k: v["label"] for k, v in QUALITY_PRESETS.items()},
        "moods": list(MUSIC_MOODS),
        "ffmpeg": _ffmpeg_version(),
        "llm": bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("OLLAMA_HOST")),
        "whisper": _module_exists("whisper"),
        "librosa": _module_exists("librosa"),
    })


def _ffmpeg_version():
    try:
        import subprocess
        out = subprocess.run([FFMPEG, "-version"], capture_output=True,
                             text=True, timeout=10).stdout
        return out.splitlines()[0] if out else None
    except Exception:  # noqa
        return None


def _module_exists(mod):
    try:
        __import__(mod)
        return True
    except ImportError:
        return False



INDEX_HTML = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n<title>EditAI Studio — Prompt-to-Video AI Editor</title>\n<link rel="stylesheet" href="/static/style.css">\n</head>\n<body>\n<header class="topbar">\n  <div class="logo"><span class="logo-dot"></span>EditAI<span class="logo-accent">Studio</span></div>\n  <nav>\n    <button class="nav-btn" id="btnProjects">Projects</button>\n    <button class="nav-btn primary" id="btnNew">+ New Edit</button>\n  </nav>\n</header>\n\n<main>\n  <!-- STEP 1 : UPLOAD -->\n  <section class="card" id="step-upload">\n    <div class="step-head"><span class="step-num">1</span><h2>Upload media</h2></div>\n    <div id="dropzone" class="dropzone">\n      <div class="dz-icon">⬆</div>\n      <p><strong>Drop videos, photos or music here</strong></p>\n      <p class="muted">MP4 · MOV · WebM · JPG · PNG · MP3 · WAV — or click to browse</p>\n      <input type="file" id="fileInput" multiple hidden\n             accept="*/*">\n    </div>\n    <div id="mediaGrid" class="media-grid"></div>\n  </section>\n\n  <!-- STEP 2 : PROMPT -->\n  <section class="card" id="step-prompt">\n    <div class="step-head"><span class="step-num">2</span><h2>Describe the edit</h2></div>\n    <div class="chips" id="templateChips"></div>\n    <textarea id="prompt" rows="3"\n      placeholder="e.g. Cinematic travel reel for Instagram with beat-synced cuts, slow motion highlights, warm color grade and bold captions…"></textarea>\n    <div class="prompt-actions">\n      <button class="btn primary" id="btnAnalyze">✦ Analyze with AI</button>\n      <span class="engine-badge" id="engineBadge" hidden></span>\n      <div class="progress-wrap" id="analyzeProgress" hidden style="flex-basis:100%">\n        <div class="progress-bar"><div class="progress-fill" id="apFill"></div></div>\n        <div class="progress-text" id="apText">Starting…</div>\n      </div>\n    </div>\n  </section>\n\n  <!-- STEP 3 : AI PLAN + TIMELINE -->\n  <section class="card" id="step-plan" hidden>\n    <div class="step-head"><span class="step-num">3</span><h2>AI edit plan — customize</h2></div>\n\n    <div class="plan-grid">\n      <label>Platform\n        <select id="selPlatform"></select></label>\n      <label>Style preset\n        <select id="selPreset"></select></label>\n      <label>Aspect ratio\n        <select id="selAspect">\n          <option value="9:16">9:16 Vertical</option>\n          <option value="16:9">16:9 Widescreen</option>\n          <option value="1:1">1:1 Square</option>\n        </select></label>\n      <label>Transitions\n        <select id="selTransition">\n          <option value="fade">Fade / Dissolve</option>\n          <option value="wipeleft">Whip pan</option>\n          <option value="glitch">Glitch</option>\n          <option value="zoompan">Punch zoom</option>\n          <option value="fadeblack">Cinematic dip</option>\n          <option value="none">Hard cuts</option>\n        </select></label>\n      <label>Music mood\n        <select id="selMood"></select></label>\n      <label>Export quality\n        <select id="selQuality">\n          <option value="high">High Quality 1080p</option>\n          <option value="4k">Master 4K</option>\n          <option value="draft">Draft (fast)</option>\n        </select></label>\n    </div>\n\n    <div class="toggles">\n      <label><input type="checkbox" id="tgRamps" checked> Speed ramps</label>\n      <label><input type="checkbox" id="tgSlowmo" checked> Slow motion</label>\n      <label><input type="checkbox" id="tgBeat" checked> Beat sync</label>\n      <label><input type="checkbox" id="tgCaps" checked> AI captions</label>\n      <label><input type="checkbox" id="tgBox"> Letterbox</label>\n    </div>\n\n    <h3 class="tl-title">Timeline <span class="muted" id="tlMeta"></span></h3>\n    <div class="timeline" id="timeline"></div>\n\n    <h3 class="tl-title">Captions</h3>\n    <div id="captionList" class="caption-list"></div>\n\n    <div class="prompt-actions">\n      <button class="btn ghost" id="btnRegen">↻ Re-cut timeline</button>\n      <button class="btn primary big" id="btnRender">▶ Generate Video</button>\n      <button class="btn ghost" id="btnSaveProject">💾 Save project</button>\n    </div>\n  </section>\n\n  <!-- STEP 4 : PREVIEW / EXPORT -->\n  <section class="card" id="step-preview" hidden>\n    <div class="step-head"><span class="step-num">4</span><h2>Preview & export</h2></div>\n    <div class="progress-wrap" id="progressWrap" hidden>\n      <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>\n      <div class="progress-text" id="progressText">Starting…</div>\n    </div>\n    <div class="preview-wrap" id="previewWrap" hidden>\n      <video id="player" controls playsinline></video>\n      <div class="preview-actions">\n        <a class="btn primary" id="btnDownload" download="editai-export.mp4">⬇ Download MP4</a>\n        <button class="btn ghost" id="btnEditPrompt">✎ Edit by prompt</button>\n        <button class="btn ghost" id="btnExport4k">⚡ Export 4K master</button>\n      </div>\n    </div>\n  </section>\n</main>\n\n<div class="toast" id="toast" hidden></div>\n<div class="modal" id="projectsModal" hidden>\n  <div class="modal-box">\n    <div class="modal-head"><h3>Saved projects</h3>\n      <button class="nav-btn" id="btnCloseProjects">✕</button></div>\n    <div id="projectList" class="project-list"></div>\n  </div>\n</div>\n\n<script src="/static/app.js"></script>\n</body>\n</html>\n'

STYLE_CSS = '[hidden]{display:none!important}\n:root{\n  --bg:#0b0d12; --bg2:#11141d; --card:#161a26; --line:#232839;\n  --txt:#e8ecf4; --muted:#8b93a7; --accent:#7c5cff; --accent2:#00e0b0;\n  --grad:linear-gradient(135deg,#7c5cff,#00e0b0);\n}\n*{box-sizing:border-box;margin:0;padding:0}\nbody{background:radial-gradient(1200px 600px at 80% -10%,rgba(124,92,255,.18),transparent),var(--bg);\n  color:var(--txt);font-family:"Inter",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;\n  min-height:100vh}\n.topbar{display:flex;align-items:center;justify-content:space-between;\n  padding:16px 28px;border-bottom:1px solid var(--line);\n  background:rgba(11,13,18,.8);backdrop-filter:blur(12px);\n  position:sticky;top:0;z-index:10}\n.logo{font-size:20px;font-weight:800;letter-spacing:.5px;display:flex;align-items:center;gap:9px}\n.logo-dot{width:12px;height:12px;border-radius:50%;background:var(--grad);box-shadow:0 0 14px var(--accent)}\n.logo-accent{background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent}\nnav{display:flex;gap:10px}\nmain{max-width:980px;margin:0 auto;padding:28px 20px 80px;display:flex;flex-direction:column;gap:22px}\n.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px;\n  box-shadow:0 10px 40px rgba(0,0,0,.35);animation:rise .35s ease}\n@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}\n.step-head{display:flex;align-items:center;gap:12px;margin-bottom:18px}\n.step-num{width:28px;height:28px;border-radius:8px;background:var(--grad);\n  display:grid;place-items:center;font-weight:800;font-size:14px;color:#0b0d12;flex:none}\nh2{font-size:18px;font-weight:700}\n.muted{color:var(--muted);font-size:13px}\n.dropzone{border:2px dashed var(--line);border-radius:12px;padding:38px 20px;text-align:center;\n  cursor:pointer;transition:.2s}\n.dropzone:hover,.dropzone.over{border-color:var(--accent);background:rgba(124,92,255,.06)}\n.dz-icon{font-size:30px;margin-bottom:8px}\n.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px;margin-top:16px}\n.thumb{position:relative;border-radius:10px;overflow:hidden;border:1px solid var(--line);\n  aspect-ratio:9/13;background:#000}\n.thumb video,.thumb img{width:100%;height:100%;object-fit:cover}\n.thumb .tag{position:absolute;top:6px;left:6px;font-size:10px;font-weight:700;\n  background:rgba(0,0,0,.65);padding:2px 7px;border-radius:6px}\n.thumb .dur{position:absolute;bottom:6px;right:6px;font-size:10px;background:rgba(0,0,0,.65);\n  padding:2px 6px;border-radius:6px}\n.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}\n.chip{border:1px solid var(--line);background:var(--bg2);color:var(--txt);padding:6px 12px;\n  border-radius:999px;font-size:12px;cursor:pointer;transition:.15s}\n.chip:hover{border-color:var(--accent);color:#fff}\ntextarea{width:100%;background:var(--bg2);border:1px solid var(--line);border-radius:12px;\n  color:var(--txt);padding:14px;font-size:15px;resize:vertical;font-family:inherit}\ntextarea:focus{outline:none;border-color:var(--accent)}\n.prompt-actions{display:flex;align-items:center;gap:12px;margin-top:14px;flex-wrap:wrap}\n.btn{border:none;border-radius:10px;padding:11px 20px;font-size:14px;font-weight:600;\n  cursor:pointer;color:var(--txt);background:var(--bg2);border:1px solid var(--line);transition:.15s;text-decoration:none;display:inline-block}\n.btn:hover{transform:translateY(-1px)}\n.btn.primary{background:var(--grad);color:#0b0d12;border:none}\n.btn.big{font-size:16px;padding:14px 28px}\n.btn.ghost{background:transparent}\n.btn:disabled{opacity:.45;cursor:not-allowed;transform:none}\n.engine-badge{font-size:12px;color:var(--accent2);border:1px solid rgba(0,224,176,.4);\n  padding:4px 10px;border-radius:999px}\n.plan-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}\n.plan-grid label,.toggles label{font-size:12px;color:var(--muted);display:flex;flex-direction:column;gap:6px}\n.toggles{flex-direction:row!important;display:flex!important;gap:18px;margin:16px 0;flex-wrap:wrap}\n.toggles label{flex-direction:row;align-items:center;gap:7px;color:var(--txt);font-size:13px;cursor:pointer}\nselect{background:var(--bg2);border:1px solid var(--line);border-radius:9px;color:var(--txt);\n  padding:9px 10px;font-size:13px;width:100%}\n.tl-title{font-size:14px;margin:20px 0 10px}\n.timeline{display:flex;gap:3px;overflow-x:auto;padding:10px;background:var(--bg2);\n  border-radius:12px;border:1px solid var(--line);min-height:86px;align-items:stretch}\n.seg{flex:none;min-width:64px;border-radius:8px;padding:8px 10px;font-size:11px;\n  background:linear-gradient(180deg,rgba(124,92,255,.35),rgba(124,92,255,.12));\n  border:1px solid rgba(124,92,255,.5);cursor:pointer;position:relative}\n.seg.slowmo{background:linear-gradient(180deg,rgba(0,224,176,.35),rgba(0,224,176,.12));\n  border-color:rgba(0,224,176,.5)}\n.seg .rm{position:absolute;top:3px;right:5px;color:#ff7b7b;cursor:pointer;font-weight:700}\n.seg input{width:52px;background:rgba(0,0,0,.4);border:1px solid var(--line);color:var(--txt);\n  border-radius:5px;font-size:10px;padding:2px 4px;margin-top:3px}\n.caption-list{display:flex;flex-direction:column;gap:8px;max-height:220px;overflow-y:auto}\n.cap-row{display:flex;gap:8px;align-items:center;background:var(--bg2);\n  border:1px solid var(--line);border-radius:9px;padding:8px 10px}\n.cap-row input[type=text]{flex:1;background:transparent;border:none;color:var(--txt);font-size:13px}\n.cap-row input[type=text]:focus{outline:none}\n.cap-row .tc{color:var(--accent2);font-size:12px;font-variant-numeric:tabular-nums;width:88px}\n.progress-wrap{margin-bottom:16px}\n.progress-bar{height:10px;border-radius:99px;background:var(--bg2);overflow:hidden;border:1px solid var(--line)}\n.progress-fill{height:100%;width:0;background:var(--grad);transition:width .3s}\n.progress-text{margin-top:8px;font-size:13px;color:var(--muted)}\n.preview-wrap{display:flex;flex-direction:column;gap:14px;align-items:center}\nvideo{width:100%;max-height:64vh;border-radius:12px;background:#000;border:1px solid var(--line)}\n.preview-actions{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}\n.toast{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);background:#1d2230;\n  border:1px solid var(--accent);padding:12px 22px;border-radius:12px;font-size:14px;z-index:99;\n  box-shadow:0 8px 30px rgba(0,0,0,.5)}\n.modal{position:fixed;inset:0;background:rgba(0,0,0,.6);display:grid;place-items:center;z-index:50}\n.modal-box{background:var(--card);border:1px solid var(--line);border-radius:16px;\n  width:min(520px,92vw);max-height:70vh;overflow:auto;padding:20px}\n.modal-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}\n.project-list{display:flex;flex-direction:column;gap:8px}\n.proj-row{display:flex;justify-content:space-between;align-items:center;\n  background:var(--bg2);border:1px solid var(--line);border-radius:10px;padding:12px 14px;cursor:pointer}\n.proj-row:hover{border-color:var(--accent)}\n.nav-btn{background:var(--bg2);border:1px solid var(--line);color:var(--txt);\n  padding:8px 14px;border-radius:9px;cursor:pointer;font-size:13px}\n.nav-btn.primary{background:var(--grad);color:#0b0d12;border:none;font-weight:700}\n'

APP_JS = '/* EditAI Studio frontend — drives Upload → Prompt → Analyze → Timeline → Render */\nconst $ = id => document.getElementById(id);\nconst state = { session: null, media: [], music: [], plan: null, captions: [], jobPoll: null };\n\nconst TEMPLATES = [\n  "Cinematic Instagram Reel with beat-synced cuts, slow motion and warm grade",\n  "High-energy gaming montage with glitch transitions and bold captions",\n  "YouTube Shorts travel video, punch zooms, vibrant colors, auto captions",\n  "Moody noir fashion film with dip-to-black transitions and minimal text",\n  "TikTok car edit: speed ramps, whip pans, phonk beat sync",\n  "Clean website promo, 16:9, professional captions, corporate mood",\n];\n\nfunction toast(msg, ms = 2600) {\n  const t = $("toast"); t.textContent = msg; t.hidden = false;\n  clearTimeout(t._h); t._h = setTimeout(() => t.hidden = true, ms);\n}\nconst fmt = s => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;\n\n/* ---------- upload ---------- */\nconst dz = $("dropzone"), fi = $("fileInput");\ndz.onclick = () => fi.click();\n["dragover", "dragenter"].forEach(e => dz.addEventListener(e, ev => { ev.preventDefault(); dz.classList.add("over"); }));\n["dragleave", "drop"].forEach(e => dz.addEventListener(e, ev => { ev.preventDefault(); dz.classList.remove("over"); }));\ndz.addEventListener("drop", ev => uploadFiles(ev.dataTransfer.files));\nfi.onchange = () => uploadFiles(fi.files);\n\nasync function uploadFiles(files) {\n  for (const file of files) await uploadOne(file);\n}\n\nasync function uploadOne(file) {\n  const CHUNK = 8 * 1024 * 1024;\n  const total = Math.max(1, Math.ceil(file.size / CHUNK));\n  const init = await (await fetch("/api/upload_init", {\n    method: "POST", headers: { "Content-Type": "application/json" },\n    body: JSON.stringify({ session: state.session || "" })\n  })).json();\n  state.session = init.session;\n  for (let i = 0; i < total; i++) {\n    const blob = file.slice(i * CHUNK, Math.min(file.size, (i + 1) * CHUNK));\n    let ok = false;\n    for (let attempt = 0; attempt < 3 && !ok; attempt++) {\n      try {\n        const fd = new FormData();\n        fd.append("session", state.session);\n        fd.append("index", i);\n        fd.append("chunk", blob);\n        const r = await fetch("/api/upload_chunk", { method: "POST", body: fd });\n        ok = r.ok;\n      } catch (e) { ok = false; }\n      if (!ok) await new Promise(res => setTimeout(res, 1500));\n    }\n    if (!ok) { toast(`Upload failed on ${file.name} (piece ${i + 1}/${total}) — try again`, 6000); return; }\n    toast(`${file.name}: ${Math.round((i + 1) / total * 100)}% uploaded`);\n  }\n  const fin = await (await fetch("/api/upload_commit", {\n    method: "POST", headers: { "Content-Type": "application/json" },\n    body: JSON.stringify({ session: state.session, name: file.name, size: file.size })\n  })).json();\n  if (fin.skipped) { toast(fin.reason || "That file cannot be edited", 6000); return; }\n  if (fin.error || !fin.entry) { toast("Upload failed: " + (fin.description || fin.error || "unknown"), 6000); return; }\n  if (fin.kind === "music") { state.music.push({ path: fin.entry.path, name: fin.entry.name }); toast(`Music added: ${fin.entry.name}`); }\n  else { state.media.push(fin.entry); renderMediaGrid(); toast(`Added: ${fin.entry.name} (${(fin.bytes / 1048576).toFixed(1)} MB, verified ✔)`); }\n}\n\nfunction renderMediaGrid() {\n  $("mediaGrid").innerHTML = state.media.map(m => `\n    <div class="thumb">\n      ${m.type === "image"\n        ? `<img src="${m.url}" loading="lazy">`\n        : `<video src="${m.url}" muted preload="metadata"></video>`}\n      <span class="tag">${m.type === "image" ? "PHOTO" : "VIDEO"}</span>\n      ${m.duration ? `<span class="dur">${fmt(m.duration)}</span>` : ""}\n    </div>`).join("");\n}\n\n/* ---------- templates ---------- */\n$("templateChips").innerHTML = TEMPLATES.map(t =>\n  `<button class="chip">${t}</button>`).join("");\ndocument.querySelectorAll(".chip").forEach(c =>\n  c.onclick = () => { $("prompt").value = c.textContent; $("prompt").focus(); });\n\n/* ---------- analyze (background job with live %) ---------- */\n$("btnAnalyze").onclick = analyze;\nasync function analyze() {\n  const prompt = $("prompt").value.trim();\n  if (!prompt) return toast("Describe the edit you want first");\n  if (!state.media.length) return toast("Upload at least one video or photo");\n  $("btnAnalyze").disabled = true;\n  $("analyzeProgress").hidden = false;\n  try {\n    const r = await fetch("/api/analyze", {\n      method: "POST", headers: { "Content-Type": "application/json" },\n      body: JSON.stringify({ prompt, session: state.session })\n    });\n    const d = await r.json();\n    if (d.description) throw new Error(d.description);\n    clearInterval(state.anaPoll);\n    state.anaPoll = setInterval(async () => {\n      const st = await (await fetch(`/api/job/${d.job}`)).json();\n      $("apFill").style.width = st.progress + "%";\n      $("apText").textContent = `${st.progress}% — ${st.message}`;\n      if (st.status === "done") {\n        clearInterval(state.anaPoll);\n        $("analyzeProgress").hidden = true;\n        onAnalyzed(st.result);\n      } else if (st.status === "error") {\n        clearInterval(state.anaPoll);\n        $("analyzeProgress").hidden = true;\n        $("btnAnalyze").disabled = false;\n        toast("Analysis failed: " + st.message, 6000);\n      }\n    }, 1000);\n  } catch (e) {\n    $("analyzeProgress").hidden = true;\n    $("btnAnalyze").disabled = false;\n    toast("Analysis failed: " + e.message, 6000);\n  }\n}\n\nfunction onAnalyzed(d) {\n    state.plan = d.plan; state.captions = d.captions || [];\n    fillControls(d);\n    renderTimeline(); renderCaptions();\n    $("step-plan").hidden = false;\n    $("engineBadge").hidden = false;\n    $("engineBadge").textContent = d.plan.engine === "llm" ? "🧠 LLM planner" : "⚙ rule-based planner";\n    $("btnAnalyze").disabled = false;\n    $("step-plan").scrollIntoView({ behavior: "smooth" });\n}\n\nfunction fillControls(d) {\n  $("selPlatform").innerHTML = Object.entries(d.platforms).map(([k, v]) =>\n    `<option value="${k}" ${k === state.plan.platform ? "selected" : ""}>${v}</option>`).join("");\n  $("selPreset").innerHTML = Object.entries(d.presets).map(([k, v]) =>\n    `<option value="${k}" ${k === state.plan.style ? "selected" : ""}>${v}</option>`).join("");\n  $("selMood").innerHTML = d.moods.map(m =>\n    `<option ${m === state.plan.music_mood ? "selected" : ""}>${m}</option>`).join("");\n  $("selAspect").value = state.plan.aspect;\n  $("selTransition").value = state.plan.transitions;\n  $("tgRamps").checked = state.plan.speed_ramps;\n  $("tgSlowmo").checked = state.plan.slowmo;\n  $("tgBeat").checked = state.plan.beat_sync;\n  $("tgCaps").checked = state.plan.captions;\n  $("tgBox").checked = state.plan.letterbox;\n}\n\nfunction collectPlan() {\n  const p = state.plan;\n  p.platform = $("selPlatform").value; p.style = $("selPreset").value;\n  p.aspect = $("selAspect").value; p.transitions = $("selTransition").value;\n  p.music_mood = $("selMood").value;\n  p.speed_ramps = $("tgRamps").checked; p.slowmo = $("tgSlowmo").checked;\n  p.beat_sync = $("tgBeat").checked; p.captions = $("tgCaps").checked;\n  p.letterbox = $("tgBox").checked;\n  p.target_duration = state.plan.segments.reduce((a, s) => a + parseFloat(s.duration || 0), 0)\n    || p.target_duration;\n  state.captions.forEach((c, i) => {\n    const row = document.querySelector(`.cap-row[data-i="${i}"] input[type=text]`);\n    if (row) c.text = row.value;\n  });\n  return p;\n}\n\n/* ---------- timeline UI ---------- */\nfunction renderTimeline() {\n  const segs = state.plan.segments;\n  const total = segs.reduce((a, s) => a + parseFloat(s.duration || 0), 0) || 1;\n  $("tlMeta").textContent = `· ${segs.length} clips · ${fmt(total)} · ${state.plan.aspect}`;\n  $("timeline").innerHTML = segs.map((s, i) => `\n    <div class="seg ${s.slowmo ? "slowmo" : ""}" style="width:${Math.max(64, s.duration / total * 600)}px">\n      <span class="rm" data-i="${i}">✕</span>\n      <div>#${i + 1} ${s.slowmo ? "🐢 slow-mo" : ""}${s.image ? " 🖼" : ""}</div>\n      <div>speed <input type="number" step="0.05" min="0.3" max="3" value="${(+s.speed).toFixed(2)}" data-k="speed" data-i="${i}"></div>\n      <div>dur <input type="number" step="0.1" min="0.3" value="${(+s.duration).toFixed(1)}" data-k="duration" data-i="${i}">s</div>\n    </div>`).join("");\n  document.querySelectorAll(".seg .rm").forEach(b => b.onclick = () => {\n    state.plan.segments.splice(+b.dataset.i, 1); renderTimeline();\n  });\n  document.querySelectorAll(".seg input").forEach(inp => inp.onchange = () => {\n    const s = state.plan.segments[+inp.dataset.i];\n    s[inp.dataset.k] = parseFloat(inp.value) || s[inp.dataset.k];\n  });\n}\n\nfunction renderCaptions() {\n  $("captionList").innerHTML = state.captions.map((c, i) => `\n    <div class="cap-row" data-i="${i}">\n      <span class="tc">${fmt(c.start)} → ${fmt(c.end)}</span>\n      <input type="text" value="${String(c.text).replace(/"/g, "&quot;")}">\n    </div>`).join("") || `<p class="muted">No captions (enable AI captions or write a prompt with keywords).</p>`;\n}\n\n$("btnRegen").onclick = async () => {\n  collectPlan();\n  const r = await fetch("/api/analyze", {\n    method: "POST", headers: { "Content-Type": "application/json" },\n    body: JSON.stringify({ prompt: state.plan.prompt + " (re-cut)", session: state.session })\n  });\n  const d = await r.json();\n  state.plan.segments = d.plan.segments; renderTimeline(); toast("Timeline re-cut");\n};\n\n/* ---------- render / preview / export ---------- */\nasync function startRender(quality) {\n  const plan = collectPlan();\n  $("step-preview").hidden = false;\n  $("previewWrap").hidden = true; $("progressWrap").hidden = false;\n  $("step-preview").scrollIntoView({ behavior: "smooth" });\n  const r = await fetch("/api/render", {\n    method: "POST", headers: { "Content-Type": "application/json" },\n    body: JSON.stringify({\n      plan, session: state.session,\n      captions: plan.captions ? state.captions : null,\n      music_path: state.music[0] ? state.music[0].path : null,\n      quality, title: plan.prompt.slice(0, 60)\n    })\n  });\n  const d = await r.json();\n  clearInterval(state.jobPoll);\n  state.jobPoll = setInterval(() => pollJob(d.job), 1200);\n}\n$("btnRender").onclick = () => startRender($("selQuality").value);\n$("btnExport4k").onclick = () => startRender("4k");\n\nasync function pollJob(id) {\n  const st = await (await fetch(`/api/job/${id}`)).json();\n  $("progressFill").style.width = st.progress + "%";\n  $("progressText").textContent = `${st.progress}% — ${st.message}`;\n  if (st.status === "done") {\n    clearInterval(state.jobPoll);\n    $("progressWrap").hidden = true; $("previewWrap").hidden = false;\n    $("player").src = st.output; $("btnDownload").href = st.output;\n    toast("Render complete — preview & download ready");\n  } else if (st.status === "error") {\n    clearInterval(state.jobPoll);\n    toast("Render failed: " + st.message, 5000);\n  }\n}\n\n$("btnEditPrompt").onclick = () => {\n  $("prompt").focus();\n  $("step-prompt").scrollIntoView({ behavior: "smooth" });\n  toast("Tweak the prompt or timeline, then Generate again");\n};\n\n/* ---------- projects ---------- */\n$("btnSaveProject").onclick = async () => {\n  const plan = collectPlan();\n  const r = await fetch("/api/project/save", {\n    method: "POST", headers: { "Content-Type": "application/json" },\n    body: JSON.stringify({\n      name: plan.prompt.slice(0, 48), plan,\n      captions: state.captions, session: state.session,\n      media: state.media.map(m => m.path)\n    })\n  });\n  toast("Project saved — id " + (await r.json()).id);\n};\n$("btnProjects").onclick = async () => {\n  const list = await (await fetch("/api/projects")).json();\n  $("projectList").innerHTML = list.map(p =>\n    `<div class="proj-row" data-id="${p.id}">\n       <div><strong>${p.name}</strong><div class="muted">${p.platform || ""} · ${new Date(p.updated_at * 1000).toLocaleString()}</div></div>\n       <span>→</span></div>`).join("") || `<p class="muted">No saved projects yet.</p>`;\n  document.querySelectorAll(".proj-row").forEach(row => row.onclick = () => loadProject(row.dataset.id));\n  $("projectsModal").hidden = false;\n};\n$("btnCloseProjects").onclick = () => $("projectsModal").hidden = true;\nasync function loadProject(id) {\n  const d = await (await fetch(`/api/project/${id}`)).json();\n  state.plan = d.plan; state.captions = d.captions || [];\n  state.session = d.session;\n  $("prompt").value = d.plan.prompt;\n  const meta = await (await fetch("/api/meta")).json();\n  fillControls({ platforms: meta.platforms, presets: meta.presets, moods: meta.moods });\n  renderTimeline(); renderCaptions();\n  $("step-plan").hidden = false; $("projectsModal").hidden = true;\n  toast("Project loaded — regenerate to re-render");\n}\n$("btnNew").onclick = () => location.reload();\n$("projectsModal").onclick = e => { if (e.target === $("projectsModal")) $("projectsModal").hidden = true; };\n\n/* ---------- boot ---------- */\n(async () => {\n  const meta = await (await fetch("/api/meta")).json();\n  if (!meta.ffmpeg) toast("⚠ ffmpeg not found on PATH — rendering is unavailable", 6000);\n  else console.log("Backend:", meta.ffmpeg, "| LLM:", meta.llm, "| Whisper:", meta.whisper, "| librosa:", meta.librosa);\n})();\n'

@app.route("/")
def _index():
    return INDEX_HTML

@app.route("/static/style.css")
def _css():
    return Response(STYLE_CSS, mimetype="text/css")

@app.route("/static/app.js")
def _js():
    return Response(APP_JS, mimetype="application/javascript")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("EditAI Studio → http://localhost:%s", port)
    app.run(host="0.0.0.0", port=port, threaded=True)
