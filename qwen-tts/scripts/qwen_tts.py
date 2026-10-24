#!/usr/bin/env python3
"""Qwen3-TTS (阿里云百炼 DashScope) 配音脚本，仅依赖标准库。

单段：
  python qwen_tts.py say "要合成的文本" -o out.wav [--voice Cherry] [--lang Chinese]
  python qwen_tts.py say -f script.txt -o out.mp3
多段（视频旁白，每段一个文件 + manifest.json 记录时长）：
  python qwen_tts.py batch segments.json -d voiceover/
列音色：
  python qwen_tts.py voices

API Key 取环境变量 DASHSCOPE_API_KEY（Windows 用户级环境变量也会读）。
"""
import argparse
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave

ENDPOINTS = {
    "cn": "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    "intl": "https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
}
SS_ENDPOINTS = {
    "cn": "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
    "intl": "https://dashscope-intl.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer",
}
DEFAULT_MODEL = "qwen-audio-3.1-tts-flash"
DEFAULT_VOICE = "anmingyuan_v3.1"
MAX_CHARS = 600  # 接口单次 text 上限
CHUNK_CHARS = 280  # 切分目标长度，留余量且句子更自然

# voice, 中文名, 风格, 方言
VOICES = [
    ("Cherry", "芊悦", "女·开朗亲切年轻女声", ""),
    ("Serena", "苏瑶", "女·温柔", ""),
    ("Ethan", "晨煦", "男·阳光活力，略带北方口音", ""),
    ("Chelsie", "千雪", "女·二次元", ""),
    ("Momo", "茉兔", "女·俏皮撒娇", ""),
    ("Vivian", "十三", "女·个性小暴躁", ""),
    ("Moon", "月白", "男·爽朗帅气", ""),
    ("Maia", "四月", "女·知性温柔", ""),
    ("Kai", "凯", "男·轻柔舒缓", ""),
    ("Nofish", "不吃鱼", "男·不带翘舌音", ""),
    ("Bella", "萌宝", "女·童趣萝莉", ""),
    ("Jennifer", "詹妮弗", "女·美式英语电影感", ""),
    ("Ryan", "甜茶", "男·节奏感强有戏剧张力", ""),
    ("Katerina", "卡捷琳娜", "女·成熟御姐", ""),
    ("Aiden", "艾登", "男·美式英语年轻男声", ""),
    ("Eldric Sage", "沧明子", "男·沉稳长者", ""),
    ("Mia", "乖小妹", "女·温顺乖巧", ""),
    ("Mochi", "沙小弥", "男·老成童声", ""),
    ("Bellona", "燕铮莺", "女·洪亮有力", ""),
    ("Vincent", "田叔", "男·沙哑烟嗓", ""),
    ("Bunny", "萌小姬", "女·可爱萝莉", ""),
    ("Neil", "阿闻", "男·新闻播报", ""),
    ("Elias", "墨讲师", "女·讲解授课", ""),
    ("Arthur", "徐大爷", "男·质朴说书", ""),
    ("Nini", "邻家妹妹", "女·软糯甜美", ""),
    ("Seren", "小婉", "女·舒缓助眠", ""),
    ("Pip", "顽屁小孩", "男·调皮童声", ""),
    ("Stella", "少女阿月", "女·甜美迷糊", ""),
    ("Bodega", "博德加", "男·热情西班牙大叔", ""),
    ("Sonrisa", "索尼莎", "女·热情拉美大姐", ""),
    ("Alek", "阿列克", "男·俄式", ""),
    ("Dolce", "多尔切", "男·慵懒意大利大叔", ""),
    ("Sohee", "素熙", "女·温柔韩式", ""),
    ("Ono Anna", "小野杏", "女·灵动日式少女", ""),
    ("Lenn", "莱恩", "男·德国青年", ""),
    ("Emilien", "埃米尔安", "男·浪漫法式", ""),
    ("Andre", "安德雷", "男·磁性沉稳", ""),
    ("Radio Gol", "拉迪奥·戈尔", "男·足球解说", ""),
    ("Jada", "上海-阿珍", "女·沪上阿姐", "上海话"),
    ("Dylan", "北京-晓东", "男·胡同少年", "北京话"),
    ("Li", "南京-老李", "男·耐心", "南京话"),
    ("Marcus", "陕西-秦川", "男·老陕厚实", "陕西话"),
    ("Roy", "闽南-阿杰", "男·诙谐直爽", "闽南语"),
    ("Peter", "天津-李彼得", "男·相声捧哏", "天津话"),
    ("Sunny", "四川-晴儿", "女·甜美川妹子", "四川话"),
    ("Eric", "四川-程川", "男·成都市井", "四川话"),
    ("Rocky", "粤语-阿强", "男·幽默风趣", "粤语"),
    ("Kiki", "粤语-阿清", "女·甜美港妹", "粤语"),
]


def api_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "DASHSCOPE_API_KEY")[0]
        except OSError:
            pass
    if not key:
        sys.exit("缺少 DASHSCOPE_API_KEY：到 https://bailian.console.aliyun.com/ 创建 API Key，"
                 "再执行 setx DASHSCOPE_API_KEY sk-xxx（重开终端生效）")
    return key


def split_text(text, limit=CHUNK_CHARS):
    """按句末标点切成不超过 limit 的块；单句过长再按逗号、最后硬切。"""
    text = re.sub(r"[ \t]+", " ", text.strip())
    sentences = [s for s in re.split(r"(?<=[。！？!?；;…\n])", text) if s.strip()]
    pieces = []
    for s in sentences:
        while len(s) > limit:
            cut = max(s.rfind(c, 0, limit) for c in "，,、：: ")
            cut = cut + 1 if cut > limit // 3 else limit
            pieces.append(s[:cut])
            s = s[cut:]
        pieces.append(s)
    chunks, cur = [], ""
    for p in pieces:
        if cur and len(cur) + len(p) > limit:
            chunks.append(cur)
            cur = ""
        cur += p
    if cur.strip():
        chunks.append(cur)
    return [c.strip() for c in chunks if c.strip()]


def synth_chunk(text, voice, lang, model, instructions, region, retries=3):
    if model.startswith(("qwen-audio", "cosyvoice")):
        # Qwen-Audio-TTS / CosyVoice：SpeechSynthesizer 接口，语气用 instruction 控制
        url = SS_ENDPOINTS[region]
        body = {"model": model, "input": {"text": text, "voice": voice, "format": "wav", "sample_rate": 48000}}
        if instructions:
            body["input"]["instruction"] = instructions
    else:
        url = ENDPOINTS[region]
        body = {"model": model, "input": {"text": text, "voice": voice, "language_type": lang}}
        if instructions:
            body["input"]["instructions"] = instructions
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"},
    )
    # 直连阿里云，不走本机代理
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(retries):
        try:
            with opener.open(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            url = (data.get("output") or {}).get("audio", {}).get("url")
            if not url:
                raise RuntimeError("响应里没有音频地址: " + json.dumps(data, ensure_ascii=False)[:500])
            with opener.open(url, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit("合成失败 HTTP %s: %s" % (e.code, detail))
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            sys.exit("网络错误: %s" % e)


def read_pcm(blob):
    """手动解析 WAV。接口返回的是流式 WAV，RIFF/data 长度是 0x7FFFFFxx 占位值，
    wave 模块会按占位值算出几万秒，这里以实际字节数为准。返回 ((声道, 采样字节, 采样率), pcm)。"""
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise RuntimeError("返回的不是 WAV 音频")
    i, fmt = 12, None
    while i + 8 <= len(blob):
        cid, size = blob[i:i + 4], struct.unpack("<I", blob[i + 4:i + 8])[0]
        if cid == b"fmt ":
            _, ch, rate, _, _, bits = struct.unpack("<HHIIHH", blob[i + 8:i + 24])
            fmt = (ch, bits // 8, rate)
        elif cid == b"data":
            pcm = blob[i + 8:i + 8 + size]
            return fmt, pcm[:len(pcm) - len(pcm) % (fmt[0] * fmt[1])]
        i += 8 + size + (size & 1)
    raise RuntimeError("WAV 里没有 data 段")


def concat_wavs(blobs, gap_ms):
    """拼接并重写为头部正确的 WAV（单段也走这里，顺便修正头部）。"""
    fmt, frames = None, []
    for i, b in enumerate(blobs):
        f, pcm = read_pcm(b)
        fmt = fmt or f
        frames.append(pcm)
        if gap_ms and i < len(blobs) - 1:
            frames.append(b"\x00" * int(fmt[2] * gap_ms / 1000) * fmt[0] * fmt[1])
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(fmt[0])
        w.setsampwidth(fmt[1])
        w.setframerate(fmt[2])
        w.writeframes(b"".join(frames))
    return out.getvalue()


def wav_seconds(blob):
    (ch, sw, rate), pcm = read_pcm(blob)
    return len(pcm) / float(ch * sw * rate)


def save(wav_blob, path, speed=1.0):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".wav" and speed == 1.0:
        with open(path, "wb") as f:
            f.write(wav_blob)
        return
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg and sys.platform == "win32":
        # winget 装完后未重开的终端 PATH 是旧的，按注册表里的用户 PATH 再找一次
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                ffmpeg = shutil.which("ffmpeg", path=os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        except OSError:
            pass
    if not ffmpeg:
        sys.exit("输出 %s 或调语速需要 ffmpeg（winget install Gyan.FFmpeg）" % ext)
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", "pipe:0"]
    if speed != 1.0:
        cmd += ["-filter:a", "atempo=%s" % speed]
    if ext == ".mp3":
        cmd += ["-codec:a", "libmp3lame", "-q:a", "2"]
    cmd.append(path)
    subprocess.run(cmd, input=wav_blob, check=True)


def synth(text, a):
    chunks = split_text(text)
    for c in chunks:
        assert len(c) <= MAX_CHARS
    blobs = [synth_chunk(c, a.voice, a.lang, a.model, a.instructions, a.region) for c in chunks]
    return concat_wavs(blobs, a.gap), len(chunks)


def cmd_say(a):
    text = open(a.file, encoding="utf-8").read() if a.file else a.text
    if not text or not text.strip():
        sys.exit("没有要合成的文本")
    blob, n = synth(text, a)
    save(blob, a.output, a.speed)
    print(json.dumps({"file": os.path.abspath(a.output), "seconds": round(wav_seconds(blob) / a.speed, 3),
                      "chunks": n, "voice": a.voice}, ensure_ascii=False))


def cmd_batch(a):
    spec = json.load(open(a.spec, encoding="utf-8"))
    segments = spec["segments"] if isinstance(spec, dict) else spec
    defaults = spec if isinstance(spec, dict) else {}
    os.makedirs(a.dir, exist_ok=True)
    manifest, cursor = [], 0.0
    for i, seg in enumerate(segments, 1):
        if isinstance(seg, str):
            seg = {"text": seg}
        sa = argparse.Namespace(**vars(a))
        for k in ("voice", "lang", "model", "instructions", "speed"):
            v = seg.get(k, defaults.get(k))
            if v is not None:
                setattr(sa, k, v)
        sid = str(seg.get("id") or "%02d" % i)
        path = os.path.join(a.dir, "%s.%s" % (sid, a.format))
        blob, _ = synth(seg["text"], sa)
        save(blob, path, sa.speed)
        secs = round(wav_seconds(blob) / sa.speed, 3)
        manifest.append({"id": sid, "file": os.path.abspath(path), "start": round(cursor, 3),
                         "seconds": secs, "voice": sa.voice, "text": seg["text"]})
        print("[%d/%d] %s %.2fs" % (i, len(segments), path, secs), file=sys.stderr)
        cursor += secs + a.pause / 1000.0
    mpath = os.path.join(a.dir, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump({"segments": manifest, "total_seconds": round(cursor - a.pause / 1000.0, 3)},
                  f, ensure_ascii=False, indent=2)
    print(json.dumps({"manifest": os.path.abspath(mpath), "segments": len(manifest),
                      "total_seconds": round(cursor - a.pause / 1000.0, 3)}, ensure_ascii=False))


MUSIC_MODEL = "qwen-audio-3.1-tts-next"  # 统一音频生成：音乐 / 音效 / 环境音；单次最长约 120s


def find_ffmpeg():
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg and sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                ffmpeg = shutil.which("ffmpeg", path=os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
        except OSError:
            pass
    return ffmpeg


def cmd_music(a):
    """配乐 / 音效：qwen-audio-3.1-tts-next 的字段是 text_prompt（不是 text，也不需要 voice），按生成秒数计费。"""
    prompt = open(a.file, encoding="utf-8").read() if a.file else a.prompt
    if not prompt:
        sys.exit("没有描述（prompt）")
    body = {"model": MUSIC_MODEL, "input": {"text_prompt": prompt, "format": "wav"}}
    req = urllib.request.Request(SS_ENDPOINTS[a.region], data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"Authorization": "Bearer " + api_key(), "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=900) as r:  # 生成 120s 音乐约需 2 分多钟
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit("生成失败 HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:500]))
    with opener.open(data["output"]["audio"]["url"], timeout=300) as r:
        blob = r.read()
    raw = os.path.splitext(a.output)[0] + ".raw.wav" if a.loop_to else a.output
    os.makedirs(os.path.dirname(os.path.abspath(raw)) or ".", exist_ok=True)
    with open(raw, "wb") as f:
        f.write(blob)
    seconds = float(data["output"]["audio"].get("duration") or 0)
    if a.loop_to:
        # 首尾交叉淡化循环到目标长度，开头淡入、结尾淡出
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            sys.exit("--loop-to 需要 ffmpeg")
        n = max(1, int(a.loop_to // max(seconds - a.xfade, 1)) + 1)
        chain = "[0]" if n == 1 else ""
        for i in range(1, n):
            chain += f"{'[0]' if i == 1 else f'[x{i - 1}]'}[{i}]acrossfade=d={a.xfade}:c1=tri:c2=tri[x{i}];"
        last = "[0]" if n == 1 else f"[x{n - 1}]"
        fc = (chain if n > 1 else "") + f"{last}atrim=0:{a.loop_to},afade=t=in:st=0:d={a.fade_in},afade=t=out:st={a.loop_to - a.fade_out}:d={a.fade_out}[out]"
        cmd = [ffmpeg, "-v", "error", "-y"] + sum([["-i", raw] for _ in range(n)], []) + ["-filter_complex", fc, "-map", "[out]", a.output]
        subprocess.run(cmd, check=True)
        seconds = a.loop_to
    print(json.dumps({"file": os.path.abspath(a.output), "seconds": seconds, "usage": data.get("usage")}, ensure_ascii=False))


def cmd_clone(a):
    """声音复刻：样音传百炼临时 OSS → voice-enrollment 建音色，得到可直接当 --voice 用的 voice_id（2026-10-21 实测）。
    tts-next 每次调用音色都会变，要固定音色就先用它生成一段满意的样音，再复刻成 flash 的音色。"""
    host = SS_ENDPOINTS[a.region].split("/api/")[0]
    key = api_key()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        # 1) 取临时上传凭证（48 小时有效的 oss:// 地址，复刻接口要求公网可访问的样音）
        req = urllib.request.Request(host + "/api/v1/uploads?action=getPolicy&model=voice-enrollment",
                                     headers={"Authorization": "Bearer " + key})
        pol = json.loads(opener.open(req, timeout=60).read())["data"]
        objkey = "%s/%s" % (pol["upload_dir"], os.path.basename(a.sample))
        boundary = "----qwentts%d" % int(time.time() * 1000)
        fields = {"OSSAccessKeyId": pol["oss_access_key_id"], "Signature": pol["signature"], "policy": pol["policy"],
                  "x-oss-object-acl": pol["x_oss_object_acl"], "x-oss-forbid-overwrite": pol["x_oss_forbid_overwrite"],
                  "key": objkey, "success_action_status": "200"}
        body = b"".join(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (boundary, k, v)).encode()
                        for k, v in fields.items())
        body += ('--%s\r\nContent-Disposition: form-data; name="file"; filename="%s"\r\nContent-Type: audio/wav\r\n\r\n'
                 % (boundary, os.path.basename(a.sample))).encode()
        body += open(a.sample, "rb").read() + ("\r\n--%s--\r\n" % boundary).encode()
        opener.open(urllib.request.Request(pol["upload_host"], data=body,
                                           headers={"Content-Type": "multipart/form-data; boundary=" + boundary}), timeout=120).read()
        # 2) 创建复刻音色
        body = {"model": "voice-enrollment", "input": {"action": "create_voice", "target_model": a.target_model,
                                                       "prefix": a.prefix, "url": "oss://" + objkey, "language_hints": [a.lang_hint]}}
        req = urllib.request.Request(host + "/api/v1/services/audio/tts/customization", json.dumps(body).encode("utf-8"),
                                     {"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                      "X-DashScope-OssResourceResolve": "enable"})
        r = json.loads(opener.open(req, timeout=120).read())
    except urllib.error.HTTPError as e:
        sys.exit("复刻失败 HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:500]))
    voice_id = r["output"]["voice_id"]
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(voice_id)
    print(json.dumps({"voice_id": voice_id, "target_model": a.target_model}, ensure_ascii=False))


def cmd_voices(a):
    for v, cn, style, dialect in VOICES:
        if a.dialect and not dialect:
            continue
        print("%-12s %-10s %s%s" % (v, cn, style, ("  [" + dialect + "]") if dialect else ""))


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Qwen3-TTS 配音")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--voice", default=DEFAULT_VOICE)
    common.add_argument("--lang", default="Chinese",
                        help="Chinese/English/Japanese/Korean/German/French/Russian/Italian/Spanish/Portuguese/Auto")
    common.add_argument("--model", default=DEFAULT_MODEL,
                        help="qwen-audio-3.1-tts-flash（默认，音色带 _v3.1 后缀）/ qwen3-tts-flash（方言音色 Dylan、Sunny 等）")
    common.add_argument("--instructions", help="语气指令（自然语言），qwen-audio / cosyvoice 模型生效")
    common.add_argument("--speed", type=float, default=1.0, help="后期变速 0.5~2.0（ffmpeg atempo，不变调）")
    common.add_argument("--gap", type=int, default=150, help="长文本切块拼接时的间隔毫秒")
    common.add_argument("--region", choices=ENDPOINTS, default="cn")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("say", parents=[common], help="合成一段")
    s.add_argument("text", nargs="?")
    s.add_argument("-f", "--file", help="从 UTF-8 文本文件读")
    s.add_argument("-o", "--output", required=True, help=".wav / .mp3 / .m4a")
    s.set_defaults(fn=cmd_say)

    b = sub.add_parser("batch", parents=[common], help="多段旁白")
    b.add_argument("spec", help='JSON: ["段1", ...] 或 {"voice":..,"segments":[{"id","text","voice"?}]}')
    b.add_argument("-d", "--dir", required=True)
    b.add_argument("--format", default="wav", choices=["wav", "mp3", "m4a"])
    b.add_argument("--pause", type=int, default=300, help="manifest 里段与段之间预留的停顿毫秒")
    b.set_defaults(fn=cmd_batch)

    mu = sub.add_parser("music", help="生成配乐 / 音效（qwen-audio-3.1-tts-next）")
    mu.add_argument("prompt", nargs="?", help="中文描述，例：纯音乐不要人声，空灵电子音色与合成器琶音……")
    mu.add_argument("-f", "--file", help="从 UTF-8 文本文件读描述")
    mu.add_argument("-o", "--output", required=True, help=".wav / .mp3")
    mu.add_argument("--loop-to", type=float, help="交叉淡化循环到这么多秒（单次生成最长约 120s）")
    mu.add_argument("--xfade", type=float, default=4.0, help="循环接缝交叉淡化秒数")
    mu.add_argument("--fade-in", type=float, default=2.0)
    mu.add_argument("--fade-out", type=float, default=4.0)
    mu.add_argument("--region", choices=ENDPOINTS, default="cn")
    mu.set_defaults(fn=cmd_music)

    c = sub.add_parser("clone", help="声音复刻：样音 wav → 固定音色 voice_id")
    c.add_argument("sample", help="样音 wav（10～20 秒内、干净无配乐）")
    c.add_argument("--prefix", required=True, help="音色名前缀，小写字母数字，如 myvoice1")
    c.add_argument("--target-model", default=DEFAULT_MODEL, help="合成时用的模型，必须与之后 say/batch 的 --model 一致")
    c.add_argument("--lang-hint", default="zh")
    c.add_argument("-o", "--output", help="把 voice_id 写进这个文件")
    c.add_argument("--region", choices=ENDPOINTS, default="cn")
    c.set_defaults(fn=cmd_clone)

    v = sub.add_parser("voices", help="列出音色")
    v.add_argument("--dialect", action="store_true", help="只看方言音色")
    v.set_defaults(fn=cmd_voices)

    a = p.parse_args()
    if not 0.5 <= getattr(a, "speed", 1.0) <= 2.0:
        sys.exit("--speed 取值 0.5~2.0")
    a.fn(a)


if __name__ == "__main__":
    main()
