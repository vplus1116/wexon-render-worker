#!/usr/bin/env python3
"""T1 рекламный ролик: сцены (картинка + озвучка) -> вертикальный монтаж 1080x1920.
Картинки показываются ВЕСЬ ролик (re-encode concat), динамичный Ken Burns,
брендовые субтитры, чистый звук, фоновая музыка.
manifest = {"scenes":[{"image","audio","text"}], "music":path|null, "out":path}
"""
import sys, os, json, subprocess, tempfile

W, H, FPS = 1080, 1920, 25

def ffprobe_dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", path],
                       capture_output=True, text=True)
    try:
        return max(1.2, float(r.stdout.strip()))
    except Exception:
        return 3.0

def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True, text=True)

def srt_time(t):
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

def make_scene(img, dur, out, idx):
    """Вертикальный клип: размытый фон + картинка + надёжный Ken Burns (зум in/out + пан)."""
    frames = int(dur * FPS) + 1
    fade_out = max(0.0, dur - 0.5)
    # линейные выражения по номеру кадра on — без условных веток, стабильно
    if idx % 2 == 0:
        zexpr = "z='min(1.0+0.0011*on,1.20)'"
        xexpr = "x='iw/2-(iw/zoom/2)+sin(on/55)*25'"; yexpr = "y='ih/2-(ih/zoom/2)'"
    else:
        zexpr = "z='max(1.20-0.0011*on,1.0)'"
        xexpr = "x='iw/2-(iw/zoom/2)'"; yexpr = "y='ih/2-(ih/zoom/2)+sin(on/55)*25'"
    vf = (
        "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=26:4,eq=brightness=-0.05,setsar=1[bg];"
        "[0:v]scale=%d:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "zoompan=%s:d=%d:%s:%s:s=%dx%d:fps=%d,"
        "fade=t=in:st=0:d=0.5,fade=t=out:st=%.2f:d=0.5,setsar=1,format=yuv420p"
    ) % (W, H, W, H, W, zexpr, frames, xexpr, yexpr, W, H, FPS, fade_out)
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", "%.2f" % dur, "-i", img,
         "-filter_complex", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast",
         "-pix_fmt", "yuv420p", out])

def main():
    man = json.load(open(sys.argv[1]))
    out = man.get("out") or sys.argv[2]
    work = tempfile.mkdtemp(prefix="t1_")
    scenes = man["scenes"]
    scene_vids, srt, t = [], [], 0.0
    for i, sc in enumerate(scenes):
        d = ffprobe_dur(sc["audio"]) + 0.35
        sv = os.path.join(work, "s%d.mp4" % i)
        make_scene(sc["image"], d, sv, i)
        scene_vids.append(sv)
        srt.append("%d\n%s --> %s\n%s\n" % (i + 1, srt_time(t + 0.15), srt_time(t + d),
                                            (sc.get("text", "") or "").strip()))
        t += d
    total = t

    # СКЛЕЙКА С ПЕРЕ-КОДИРОВАНИЕМ — единый непрерывный видеопоток (картинки весь ролик)
    vlst = os.path.join(work, "v.txt")
    open(vlst, "w").write("".join("file '%s'\n" % p for p in scene_vids))
    body = os.path.join(work, "body.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", vlst,
         "-c:v", "libx264", "-preset", "veryfast", "-r", str(FPS), "-pix_fmt", "yuv420p",
         "-vsync", "cfr", body])

    # озвучка: единый формат + склейка
    awav = []
    for i, sc in enumerate(scenes):
        a2 = os.path.join(work, "a%d.wav" % i)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", sc["audio"], "-ar", "48000", "-ac", "1", a2])
        awav.append(a2)
    alst = os.path.join(work, "a.txt")
    open(alst, "w").write("".join("file '%s'\n" % p for p in awav))
    voice = os.path.join(work, "voice.wav")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", alst, "-c", "copy", voice])

    srtf = os.path.join(work, "subs.srt")
    open(srtf, "w").write("\n".join(srt))
    style = ("FontName=DejaVu Sans,Fontsize=20,Bold=1,PrimaryColour=&H00FFFFFF,"
             "BorderStyle=4,BackColour=&HA0101820,Outline=0,Shadow=0,Alignment=2,MarginV=170")

    voice_fx = ("loudnorm=I=-15:TP=-1.5:LRA=11,highpass=f=85,lowpass=f=11000,"
                "acompressor=threshold=-18dB:ratio=3:attack=8:release=180")

    music = man.get("music")
    if music and os.path.exists(music):
        fc = ("[0:v]subtitles='%s':force_style='%s'[v];"
              "[1:a]%s[a1];[2:a]volume=0.28,aloop=loop=-1:size=2000000000,afade=t=in:st=0:d=1.5[a2];"
              "[a1][a2]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]") % (srtf, style, voice_fx)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-i", voice, "-i", music,
               "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", "%.2f" % total]
    else:
        fc = "[0:v]subtitles='%s':force_style='%s'[v];[1:a]%s[a]" % (srtf, style, voice_fx)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-i", voice,
               "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", "%.2f" % total]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    run(cmd)
    print(json.dumps({"ok": True, "out": out, "duration": round(total, 2), "scenes": len(scenes)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
