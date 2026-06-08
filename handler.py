#!/usr/bin/env python3
"""WEXON T1 render worker (RunPod Serverless).

input:
{
  "scenes": [{"text": "озвучка сцены", "image_url": "https://...", "subtitle": "..."(опц)}],
  "lang": "ru",                  # ru|uk|en|es|it|zh
  "voice": "ru_RU-irina-medium", # опционально, иначе по lang
  "music_url": "https://..."     # опционально (иначе /app/music/default.mp3 если есть)
}
output: {"video_url": "<cloudinary secure_url>", "duration": <sec>, "scenes": <n>}
"""
import os, re, subprocess, tempfile, json, uuid, requests
import runpod
import cloudinary
import cloudinary.uploader

PIPER = "/app/piper/piper"
VOICES = "/app/voices"

# MVP: ru + en. Остальные языки временно маппятся (добавить native-голоса позже).
VOICE_BY_LANG = {
    "ru": "ru_RU-irina-medium",
    "uk": "ru_RU-irina-medium",
    "en": "en_US-amy-medium",
    "es": "en_US-amy-medium",
    "it": "en_US-amy-medium",
    "zh": "en_US-amy-medium",
}

# Cloudinary из env (CLOUDINARY_URL ИЛИ отдельные ключи) — парсим явно
def _init_cloudinary():
    cu = (os.environ.get("CLOUDINARY_URL") or "").strip()
    if cu:
        m = re.match(r"cloudinary://([^:]+):([^@]+)@(.+)", cu)
        if m:
            cloudinary.config(api_key=m.group(1), api_secret=m.group(2),
                              cloud_name=m.group(3), secure=True)
            return True
    cn = os.environ.get("CLOUDINARY_CLOUD_NAME")
    ak = os.environ.get("CLOUDINARY_API_KEY")
    sec = os.environ.get("CLOUDINARY_API_SECRET")
    if cn and ak and sec:
        cloudinary.config(cloud_name=cn, api_key=ak, api_secret=sec, secure=True)
        return True
    return False

CLOUD_OK = _init_cloudinary()


import numpy as np
import wave

# Silero TTS (естественный голос). Кэш моделей в памяти воркера.
_silero = {}
SILERO_SPK = {"ru": "kseniya", "en": "en_0"}

def _get_silero(key):
    if key not in _silero:
        import torch
        torch.set_num_threads(4)
        lang = "ru" if key == "ru" else "en"
        spk = "v4_ru" if key == "ru" else "v3_en"
        model, _ = torch.hub.load(repo_or_dir="snakers4/silero-models", model="silero_tts",
                                  language=lang, speaker=spk, trust_repo=True)
        model.to("cpu")
        _silero[key] = model
    return _silero[key]

def _save_wav(path, audio, sr):
    a = (np.clip(audio.numpy(), -1.0, 1.0) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(a.tobytes())

def tts(text, lang, voice, out):
    text = (text or " ").strip() or " "
    key = "ru" if lang in ("ru", "uk") else ("en" if lang in ("en", "es", "it") else None)
    if key:
        try:
            model = _get_silero(key)
            audio = model.apply_tts(text=text, speaker=SILERO_SPK[key], sample_rate=48000)
            _save_wav(out, audio, 48000)
            if os.path.getsize(out) > 1000:
                return
        except Exception as e:
            print("[tts] silero fail -> piper:", str(e)[:200], flush=True)
    subprocess.run([PIPER, "--model", "%s/%s.onnx" % (VOICES, voice), "--output_file", out],
                   input=text, text=True, capture_output=True, check=True)


def download(url, out):
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with open(out, "wb") as f:
        f.write(r.content)


def handler(job):
    inp = job.get("input", {}) or {}
    scenes = inp.get("scenes") or []
    if not scenes:
        return {"error": "no scenes"}
    if not CLOUD_OK:
        return {"error": "cloudinary not configured: задай CLOUDINARY_URL в env эндпоинта"}
    lang = inp.get("lang", "ru")
    voice = inp.get("voice") or VOICE_BY_LANG.get(lang, "en_US-amy-medium")

    work = tempfile.mkdtemp(prefix="t1_")
    man_scenes = []
    try:
        for i, sc in enumerate(scenes):
            aud = os.path.join(work, "a%d.wav" % i)
            tts(sc.get("text", ""), lang, voice, aud)
            entry = {"audio": aud, "text": sc.get("subtitle", sc.get("text", ""))}
            if sc.get("video_url"):           # T2: готовый видео-клип (Kling/LTX)
                clip = os.path.join(work, "clip%d.mp4" % i)
                download(sc["video_url"], clip)
                entry["clip"] = clip
            else:                              # T1: картинка + Ken Burns
                img = os.path.join(work, "img%d.png" % i)
                download(sc["image_url"], img)
                entry["image"] = img
            man_scenes.append(entry)

        music = None
        if inp.get("music_url"):
            try:
                music = os.path.join(work, "music.mp3")
                download(inp["music_url"], music)
            except Exception:
                music = None
        elif os.path.exists("/app/music/default.mp3"):
            music = "/app/music/default.mp3"

        out = os.path.join(work, "out.mp4")
        man = {"scenes": man_scenes, "music": music, "out": out}
        manp = os.path.join(work, "man.json")
        with open(manp, "w") as f:
            f.write(json.dumps(man, ensure_ascii=False))

        r = subprocess.run(["python", "render_t1.py", manp], capture_output=True, text=True)
        if not os.path.exists(out):
            return {"error": "render failed", "detail": (r.stderr or r.stdout)[-900:]}

        up = cloudinary.uploader.upload_large(
            out, resource_type="video", folder="wexon_t1",
            public_id="t1_%s" % uuid.uuid4().hex[:10])
        meta = {}
        try:
            meta = json.loads(r.stdout or "{}")
        except Exception:
            pass
        return {"video_url": up.get("secure_url"),
                "duration": meta.get("duration"),
                "scenes": len(scenes)}
    except Exception as e:
        return {"error": "worker exception", "detail": str(e)[-500:]}


runpod.serverless.start({"handler": handler})
