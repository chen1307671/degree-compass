"""Degree Compass - video builder

Build/verify script for the Degree Compass deliverable. See README for usage."""
from __future__ import annotations
import asyncio, json, math, os, pathlib, re, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg
import edge_tts

from src.slides_data import SLIDES, TOTAL_SCRIPT_CHARS

HERE = pathlib.Path(__file__).resolve().parent
ASSETS = HERE / "assets"
FRAMES = ASSETS / "frames"
AUDIO = ASSETS / "audio"
OUT_MP4 = HERE / "slides" / "学位罗盘_演示视频.mp4"
OUT_SRT = HERE / "slides" / "学位罗盘_演示字幕.srt"
FF = imageio_ffmpeg.get_ffmpeg_exe()

W, H = 1280, 720
PRIMARY = (0x1E, 0x4F, 0xA8)
ACCENT = (0x3D, 0x7B, 0xD9)
DARK = (0x1A, 0x22, 0x30)
GRAY = (0x6B, 0x76, 0x87)
LGRAY = (0x8B, 0x97, 0xA8)
PANEL = (0xE8, 0xEF, 0xF8)
PANEL2 = (0xF2, 0xF6, 0xFC)
LINE = (0xD6, 0xDC, 0xE5)
WHITE = (0xFF, 0xFF, 0xFF)

FD = "C:/Windows/Fonts/msyh.ttc"
FDB = "C:/Windows/Fonts/msyhbd.ttc"
# Match the deck: ASCII text in Times New Roman, Chinese in YaHei
FL = "C:/Windows/Fonts/times.ttf"
FLB = "C:/Windows/Fonts/timesbd.ttf"


def font(px, bold=False):
    return ImageFont.truetype(FDB if bold else FD, px)


def font_for(text, px, bold=False):
    """Pure ASCII uses Times New Roman; Chinese uses YaHei."""
    s = str(text)
    if s and all(ord(c) < 128 for c in s):
        try:
            return ImageFont.truetype(FLB if bold else FL, px)
        except Exception:
            return font(px, bold)
    return font(px, bold)


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for ch in text:
        if ch in "\n":
            lines.append(cur); cur = ""; continue
        t = cur + ch
        if draw.textlength(t, font=fnt) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def rr(draw, box, fill, radius=14):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def render_slide(s, idx):
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    # top colour bar
    d.rectangle([0, 0, W, 14], fill=PRIMARY)
    # page number (top right, clear of the footnote)
    d.text((W - 40, 44), f"{idx:02d} / 20", font=font_for(f"{idx:02d} / 20", 16), fill=LGRAY, anchor="rs")
    y0 = 200
    # the cover lays itself out, avoiding duplicate titles
    if not s.get("cover"):
        d.text((64, 40), s["kicker"], font=font(18, True), fill=ACCENT)
        d.text((64, 74), s["title"], font=font(40, True), fill=PRIMARY)
        if s.get("subtitle"):
            d.text((64, 134), s["subtitle"], font=font(22), fill=GRAY)
            y0 = 210
    # right column
    if s.get("cover"):
        _cover(d, s)
    else:
        _body(d, s, y0, img)
    # footnote: auto font size, leaves room for the page number
    if s.get("footnote"):
        txt = s["footnote"]
        fs = 15 if len(txt) < 90 else (13 if len(txt) < 140 else 12)
        d.line([64, 668, W - 64, 668], fill=LINE, width=1)
        y = 676
        for ln in wrap(d, txt, font(fs), W - 140)[:3]:
            d.text((64, y), ln, font=font(fs), fill=LGRAY)
            y += fs + 3
    return img


def _body(d, s, y0, img=None):
    left_x, left_w = 64, 760
    # pages that need a full image: paste the PNG as-is
    if s.get("chart_img") and s.get("chart") and img is not None:
        cp = pathlib.Path(__file__).resolve().parent / "assets" / "charts" / f'{s["chart"]}.png'
        if cp.exists():
            # text left, image right, matching the deck
            col_w = 560
            yy = y0 + 6
            for b in s.get("bullets", []):
                for ln in wrap(d, "— " + b, font(20), col_w):
                    d.text((left_x, yy), ln, font=font(20), fill=DARK)
                    yy += 30
                yy += 14
            pic = Image.open(cp).convert("RGB")
            rx = left_x + col_w + 40
            max_w, max_h = W - rx - 40, H - y0 - 96
            ratio = min(max_w / pic.width, max_h / pic.height)
            pic = pic.resize((int(pic.width * ratio), int(pic.height * ratio)), Image.LANCZOS)
            img.paste(pic, (rx, y0))
            d.rectangle([rx, y0, rx + pic.width, y0 + pic.height], outline=LINE, width=1)
            return
    # interface page: paste the real screenshot
    if s.get("ui_seq") and img is not None:
        shot_p = pathlib.Path(__file__).resolve().parent / "assets" / "charts" / "ui_real.png"
        if shot_p.exists():
            shot = Image.open(shot_p).convert("RGB")
            shot.thumbnail((404, 520))
            img.paste(shot, (836, 196))
            d.rectangle([836, 196, 836 + shot.width, 196 + shot.height], outline=LINE, width=2)
            d.text((836, 196 + shot.height + 14), "真实运行截图（本机演示实例）",
                   font=font(15), fill=LGRAY)
            left_w = 700
    if s.get("hero") and not s.get("ui_seq"):
        _hero(d, 860, y0, 360, 200, s["hero"][0], s["hero"][1])
    elif s.get("cards"):
        _cards(d, 860, y0, 360, 470, s["cards"])
    if s.get("table"):
        th = _table(d, left_x, y0, left_w, s["table"]["headers"], s["table"]["rows"])
        if s.get("bullets"):
            yy = y0 + th + 18
            yy = _bullets(d, left_x, yy, left_w, s["bullets"], 22, 9)
    elif s.get("bullets"):
        _bullets(d, left_x, y0, left_w, s["bullets"], 25, 13)


def _bullets(d, x, y, w, items, size, gap):
    f = font(size)
    for b in items:
        for ln in wrap(d, "▪ " + b, f, w):
            d.text((x, y), ln, font=f, fill=DARK)
            y += size + 8
        y += gap
    return y


def _hero(d, x, y, w, h, value, label):
    rr(d, [x, y, x + w, y + h], PANEL, 16)
    fv = font_for(value, 52, True); fl = font(20)
    d.text((x + w / 2, y + h / 2 - 22), str(value), font=fv, fill=PRIMARY, anchor="mm")
    d.text((x + w / 2, y + h / 2 + 34), str(label), font=fl, fill=GRAY, anchor="mm")


def _cards(d, x, y, w, h, cards):
    n = len(cards)
    cols = 1 if n <= 3 else 2
    rows = math.ceil(n / cols)
    gx, gy = 18, 18
    cw = (w - gx * (cols - 1)) / cols
    ch = (h - gy * (rows - 1)) / rows
    for i, c in enumerate(cards):
        r, ccol = divmod(i, cols)
        cx = x + ccol * (cw + gx)
        cy = y + r * (ch + gy)
        rr(d, [cx, cy, cx + cw, cy + ch], PANEL, 14)
        d.text((cx + cw / 2, cy + ch / 2 - 16), str(c[0]), font=font_for(c[0], 28, True),
               fill=PRIMARY, anchor="mm")
        for ln in wrap(d, str(c[1]), font(16), int(cw - 24)):
            d.text((cx + cw / 2, cy + ch / 2 + 18), ln, font=font(16),
                   fill=GRAY, anchor="mm")
            break


def _table(d, x, y, w, headers, rows):
    nrows = len(rows) + 1
    ncols = len(headers)
    col_w = [w / ncols] * ncols
    rh = 40
    hh = 44
    # header
    cx = x
    rr(d, [x, y, x + w, y + hh], PRIMARY, 6)
    for j, htext in enumerate(headers):
        d.text((cx + col_w[j] / 2, y + hh / 2), str(htext), font=font_for(htext, 18, True),
               fill=WHITE, anchor="mm")
        cx += col_w[j]
    yy = y + hh
    for i, row in enumerate(rows):
        if i:
            d.rectangle([x, yy, x + w, yy + rh], fill=PANEL2 if i % 2 else WHITE)
        else:
            d.rectangle([x, yy, x + w, yy + rh], fill=WHITE)
        cx = x
        for j, val in enumerate(row):
            d.text((cx + col_w[j] / 2, yy + rh / 2), str(val), font=font_for(val, 17),
                   fill=DARK, anchor="mm")
            cx += col_w[j]
        yy += rh
    return hh + rh * len(rows)


def _cover(d, s):
    d.text((W / 2, 120), s["title"], font=font(56, True), fill=PRIMARY, anchor="mm")
    if s.get("subtitle"):
        d.text((W / 2, 188), s["subtitle"], font=font(24), fill=GRAY, anchor="mm")
    if s.get("hero"):
        v, l = s["hero"]
        rr(d, [W / 2 - 330, 250, W / 2 + 330, 380], PANEL, 16)
        d.text((W / 2, 300), str(v), font=font_for(v, 58, True), fill=PRIMARY, anchor="mm")
        d.text((W / 2, 350), str(l), font=font(22), fill=GRAY, anchor="mm")
    if s.get("cards"):
        n = len(s["cards"]); cw, gap = 360, 40
        total = cw * n + gap * (n - 1); x0 = (W - total) / 2
        for i, c in enumerate(s["cards"]):
            cx = x0 + i * (cw + gap)
            rr(d, [cx, 430, cx + cw, 540], PANEL2, 14)
            d.text((cx + cw / 2, 475), str(c[0]), font=font(34, True), fill=PRIMARY, anchor="mm")
            d.text((cx + cw / 2, 515), str(c[1]), font=font(18), fill=GRAY, anchor="mm")
    if s.get("bullets"):
        y = 590
        for b in s["bullets"]:
            d.text((W / 2, y), "· " + b, font=font(18), fill=DARK, anchor="mm")
            y += 30


async def tts(text, out_path):
    try:
        voice = "zh-CN-XiaoxiaoNeural"
        rate = os.environ.get("TTS_RATE", "+10%")   # 语速：默认 +10% 以压缩总时长
        comm = edge_tts.Communicate(text, voice, rate=rate)
        await comm.save(str(out_path))
        return True
    except Exception as e:
        print(f"  [tts] 失败 {out_path.name}: {e}")
        return False


def make_silent(path, seconds):
    subprocess.run([FF, "-y", "-f", "lavfi", "-i", f"anullsrc=r=24000:cl=1",
                   "-t", str(seconds), "-c:a", "libmp3lame", "-q:a", "4", str(path)],
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def parse_duration(stderr):
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
    if m:
        h, mi, se = map(float, m.groups())
        return h * 3600 + mi * 60 + se
    return None


def probe_duration(path) -> float | None:
    """Read real media duration with ffmpeg -i."""
    r = subprocess.run([FF, "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return parse_duration(r.stderr.decode("utf-8", "ignore"))


def clip_from_frames(frames, audio, out, dur):
    """Join interface frames into a clip at equal duration, then merge with audio."""
    n = len(frames)
    per = dur / n
    lst = out.with_suffix(".txt")
    lines = []
    for f in frames:
        lines.append(f"file '{f.resolve()}'")
        lines.append(f"duration {per:.3f}")
    lines.append(f"file '{frames[-1].resolve()}'")
    lst.write_text("\n".join(lines), encoding="utf-8")
    silent = out.with_name(out.stem + "_v.mp4")
    subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vsync", "vfr", "-pix_fmt", "yuv420p", "-r", "25", "-an", str(silent)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([FF, "-y", "-i", str(silent), "-i", str(audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def build():
    FRAMES.mkdir(parents=True, exist_ok=True)
    AUDIO.mkdir(parents=True, exist_ok=True)
    clips = []
    durations = []
    with tempfile.TemporaryDirectory() as td:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        for i, s in enumerate(SLIDES, 1):
            fp = FRAMES / f"slide{i:02d}.png"
            render_slide(s, i).save(fp)
            ap = AUDIO / f"slide{i:02d}.mp3"
            # reuse narration audio when the script is unchanged;
            # set REBUILD_TTS=1 to force regeneration.
            reuse = (ap.exists() and ap.stat().st_size > 1000
                     and os.environ.get("REBUILD_TTS") != "1")
            ok = True if reuse else loop.run_until_complete(tts(s["script"], ap))
            if not ok or not ap.exists() or ap.stat().st_size < 1000:
                # estimate duration (about 4.5 characters per second) and build silence
                secs = max(3.0, len(s["script"]) / 4.5)
                make_silent(ap, secs)
            # compose a clip; duration follows the real audio length
            dur_audio = probe_duration(ap)
            clip = pathlib.Path(td) / f"clip{i:02d}.mp4"
            cmd = [FF, "-y", "-loop", "1", "-i", str(fp), "-i", str(ap),
                   "-c:v", "libx264", "-tune", "stillimage", "-r", "25",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                   "-shortest", "-movflags", "+faststart", str(clip)]
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            dur = probe_duration(clip) or dur_audio or max(3.0, len(s["script"]) / 4.5)
            # interface page: use the frame sequence when available
            if s.get("ui_seq"):
                seq = sorted((HERE / "assets" / "charts" / "ui_seq").glob("f*.png"))
                if len(seq) >= 2 and dur > 3:
                    try:
                        clip_from_frames(seq, ap, clip, dur)
                        dur = probe_duration(clip) or dur
                        print(f"[video] 第 16 页使用 {len(seq)} 帧真实界面")
                    except Exception as exc:  # noqa: BLE001
                        print(f"[video] 帧序列合成失败，回退单图：{type(exc).__name__}")
            durations.append(dur)
            clips.append(clip)
        # concat
        clist = pathlib.Path(td) / "list.txt"
        clist.write_text("\n".join(f"file '{c.resolve()}'" for c in clips),
                         encoding="utf-8")
        tmp_mp4 = pathlib.Path(td) / "full.mp4"
        subprocess.run([FF, "-y", "-f", "concat", "-safe", "0", "-i", str(clist),
                       "-c", "copy", str(tmp_mp4)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        OUT_MP4.parent.mkdir(parents=True, exist_ok=True)
        tmp_mp4.replace(OUT_MP4)
    # SRT
    write_srt(durations)
    # mux subtitles as a soft track
    srt_tmp = AUDIO / "_subs.srt"
    srt_tmp.write_text((OUT_SRT).read_text(encoding="utf-8"), encoding="utf-8")
    muxed = OUT_MP4.with_name("学位罗盘_演示视频_含字幕.mp4")
    r = subprocess.run([FF, "-y", "-i", str(OUT_MP4), "-i", str(OUT_SRT),
                        "-c", "copy", "-c:s", "mov_text", str(muxed)],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print(f"[video] {OUT_MP4.name}  clips={len(clips)}  total={sum(durations):.1f}s")
    print(f"[video] {OUT_SRT.name}  chars={TOTAL_SCRIPT_CHARS}")
    # metadata
    meta = dict(resolution="1280x720", codec="h264+aac", duration_seconds=round(sum(durations), 1),
                n_slides=len(SLIDES), script_chars=TOTAL_SCRIPT_CHARS,
                subtitles="学位罗盘_演示字幕.srt", muxed="学位罗盘_演示视频_含字幕.mp4")
    (HERE / "reports" / "video_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def write_srt(durations):
    t = 0.0
    lines = []
    for i, s in enumerate(SLIDES, 1):
        start = t
        end = t + durations[i - 1]
        lines.append(str(i))
        lines.append(f"{fmt(start)} --> {fmt(end)}")
        # break subtitles at punctuation to avoid overlong lines
        txt = s["script"]
        lines.append(txt)
        lines.append("")
        t = end
    OUT_SRT.parent.mkdir(parents=True, exist_ok=True)
    OUT_SRT.write_text("\n".join(lines), encoding="utf-8")


def fmt(sec):
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


if __name__ == "__main__":
    m = build()
    print(json.dumps(m, ensure_ascii=False))
