#!/usr/bin/env python3
"""T1 рекламный ролик: сцены (картинка + озвучка) -> вертикальный монтаж 1080x1920
с субтитрами и фоновой музыкой. Вход: JSON-манифест, выход: mp4.
manifest = {"scenes":[{"image":..,"audio":..,"text":..}], "music":path|null, "out":path}
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

def make_scene(img, dur, out):
    frames = int(dur * FPS) + 1
    fade_out = max(0.0, dur - 0.4)
    vf = (
        "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=24:4,setsar=1[bg];"
        "[0:v]scale=%d:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        "zoompan=z='min(zoom+0.0006,1.12)':d=%d:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=%dx%d:fps=%d,"
        "fade=t=in:st=0:d=0.4,fade=t=out:st=%.2f:d=0.4,format=yuv420p"
    ) % (W, H, W, H, W, frames, W, H, FPS, fade_out)
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
        d = ffprobe_dur(sc["audio"])
        sv = os.path.join(work, "s%d.mp4" % i)
        make_scene(sc["image"], d, sv)
        scene_vids.append(sv)
        srt.append("%d\n%s --> %s\n%s\n" % (i + 1, srt_time(t), srt_time(t + d), (sc.get("text", "") or "").strip()))
        t += d
    total = t

    vlst = os.path.join(work, "v.txt")
    open(vlst, "w").write("".join("file '%s'\n" % p for p in scene_vids))
    body = os.path.join(work, "body.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", vlst, "-c", "copy", body])

    alst = os.path.join(work, "a.txt")
    open(alst, "w").write("".join("file '%s'\n" % sc["audio"] for sc in scenes))
    voice = os.path.join(work, "voice.wav")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", alst, "-c", "copy", voice])

    srtf = os.path.join(work, "subs.srt")
    open(srtf, "w").write("\n".join(srt))
    style = ("FontName=DejaVu Sans,FontSize=15,PrimaryColour=&H00FFFFFF,OutlineColour=&HB0000000,"
             "BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=130")

    music = man.get("music")
    if music and os.path.exists(music):
        fc = ("[0:v]subtitles='%s':force_style='%s'[v];"
              "[1:a]volume=1.0[a1];[2:a]volume=0.14,aloop=loop=-1:size=2000000000[a2];"
              "[a1][a2]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]") % (srtf, style)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-i", voice, "-i", music,
               "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", "%.2f" % total]
    else:
        fc = "[0:v]subtitles='%s':force_style='%s'[v]" % (srtf, style)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-i", voice,
               "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-t", "%.2f" % total]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", out]
    run(cmd)
    print(json.dumps({"ok": True, "out": out, "duration": round(total, 2), "scenes": len(scenes)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
