---
name: qwen-tts
description: 用阿里云百炼 Qwen-Audio 合成中文（含方言）/多语种配音，并能按文字描述生成配乐、音效（qwen-audio-3.1-tts-next），输出 wav/mp3 及每段时长。用户要「配音 / 旁白 / 解说 / 朗读 / 文字转语音 / TTS / voiceover / 配乐 / 背景音乐 / 音效」时使用，包括给 HyperFrames 视频配旁白和配乐——此时优先用本 skill，不用 media-use 里的 HeyGen TTS / BGM（HeyGen CLI 不支持 Windows）。
---

# Qwen-TTS 配音

**默认模型 `qwen-audio-3.1-tts-flash`，默认音色安明远 `anmingyuan_v3.1`**（更像真人；支持 `--instructions` 自然语言语气控制，48kHz）。
新模型常用男声：`anmingyuan_v3.1` 安明远（清亮自然，广告/旁白）、`huozhuoshi_v3.1` 霍拙石（清亮，广告/有声书）、
`longsanshu_v3.1` 龙三叔（沉稳）、`longanchong_v3.1` 龙安冲（激情带货）；女声如 `longanhuan_v3.1`。
方言音色（Dylan / Sunny / Rocky 等）和下面的老音色表属于 `qwen3-tts-flash`，要用时加 `--model qwen3-tts-flash`。

脚本：`~/.claude/skills/qwen-tts/scripts/qwen_tts.py`（纯标准库；mp3/m4a 输出和变速需要 ffmpeg）。

## 前提

- API Key 只从环境变量 `DASHSCOPE_API_KEY` 读（Windows 用户级环境变量也会读，`setx` 后无需重开会话）。
  没配就停下告诉用户去 https://bailian.console.aliyun.com/ 创建，**不要**让用户把 Key 贴进对话、写进文件或命令行。
- 收费：按字符计费（约 0.8 元/万字），大批量（上万字）合成前先跟用户说一声。
- 单次接口上限 600 字，脚本自动按句子切块再拼接，不用手动拆。

## 用法

```bash
S=~/.claude/skills/qwen-tts/scripts/qwen_tts.py

# 列音色（--dialect 只看方言）
python $S voices

# 单段
python $S say "欢迎收听本期节目。" -o out.wav --voice Cherry
python $S say -f script.txt -o narration.mp3 --voice Neil --speed 1.1

# 多段旁白（视频用）：每段一个文件 + manifest.json（start/seconds）
python $S batch segments.json -d voiceover/ --format wav --pause 300
```

`segments.json` 两种写法：

```json
["第一段旁白。", "第二段旁白。"]
```

```json
{"voice": "Ethan", "segments": [
  {"id": "intro", "text": "开场白……"},
  {"id": "demo", "text": "演示……", "voice": "Cherry", "speed": 1.05}
]}
```

常用参数：`--voice`（默认 anmingyuan_v3.1）、`--lang`（仅 qwen3-tts-flash 用；默认 Chinese，英文稿 English，混合 Auto）、
`--speed 0.5~2.0`（ffmpeg 后期变速，不变调）、`--gap` 切块拼接间隔毫秒、`--region intl`（新加坡地域的 Key）。
语气控制：`--instructions "广告播音，专业冷静，有说服力"`（默认模型直接生效；batch 的每段也可写 `"instructions"`）。
需要字幕严格对齐时：一句一段合成（batch），字幕用原文、时间取 manifest 的 start/seconds，不要整篇一次合成再估算。

## 配乐 / 音效（qwen-audio-3.1-tts-next）

```bash
# 纯音乐，单次最长约 120s，耗时约 2 分钟；--loop-to 交叉淡化循环到全片长度
python $S music "纯音乐，不要人声：空灵电子音色与未来感合成器琶音铺入，随后加入克制的电子鼓，现代科技、明亮自信，中速，垫在旁白下不抢人声" -o bgm.mp3 --loop-to 244
```

- 接口字段是 `input.text_prompt`（官方文档未写，2026-10-21 实测；用 `text` 会报 `text_prompt must not be empty`），不需要 voice。
- 描述里写明「纯音乐、不要人声」；也可以描述音效 / 环境音（如「微信消息发送提示音，短促清脆」）。
- 按生成秒数计费（`usage.duration`）。旁白片子里配乐音量建议 0.05 左右，再配合 hyperframes-audio 的 voiceover carve。
- Fun-Music（`/services/audio/music/generation`）是邀请制，未开通时报 403，不要用。

## 声音复刻（固定音色）

```bash
# 样音 → voice_id；之后 say/batch 用 --voice <voice_id>，--model 与 --target-model 一致
python $S clone sample.wav --prefix myvoice1 -o voice_id.txt
python $S say "测试一句。" -o t.wav --voice "$(cat voice_id.txt)"
```

- 流程：取百炼临时上传凭证 → 样音传临时 OSS（`oss://` 地址）→ `voice-enrollment` 的 `create_voice` 建音色（请求头要带 `X-DashScope-OssResourceResolve: enable`）。
- 典型用法：tts-next 能按「年龄、音色、语速」描述生成很像真人的声音，但**每次调用音色都不一样**，整片配音会每句一个人。
  先用 tts-next 生成几段样音让用户挑，选定后复刻成 flash 音色，再逐句合成，全片音色一致。
- 样音 10～20 秒内、干净无配乐；复刻音色用原速合成，要快一点用 `--speed`（如 1.25）。

## 选音色

| 场景 | 推荐 |
|---|---|
| 产品介绍 / 宣传片 | Cherry（亲切女声）、Ethan（阳光男声）、Ryan（有张力） |
| 教程 / 讲解 | Elias（讲解授课）、Maia（知性）、Neil（播报） |
| 沉稳 / 高端 | Andre（磁性）、Serena（温柔） |
| 方言 | Dylan 北京、Jada 上海、Sunny/Eric 四川、Rocky/Kiki 粤语、Marcus 陕西、Peter 天津、Roy 闽南、Li 南京 |

完整 48 个音色跑 `voices` 看。用户没指定时，选 1～2 个候选各合成一句试听，让用户挑，别直接整篇合成。

## 配合 HyperFrames

1. 先定稿旁白，按场景拆段写 `segments.json`（id 用场景名）。
2. `batch` 合成到项目的 `assets/voiceover/`，读 `manifest.json` 的 `seconds` 决定每个场景时长——**画面跟着配音走**，不要反过来压配音。
3. 音频按 hyperframes-core 的媒体规则放进 composition；和背景音乐的混音、旁白压低 BGM 交给 `/hyperframes-audio`。
4. 改了某一段文字只重合成那一段（单段 `say` 输出同名文件），然后更新该场景时长。

## 排错

- `缺少 DASHSCOPE_API_KEY`：Key 没配，见「前提」。
- `HTTP 401 / InvalidApiKey`：Key 错了或地域不对（新加坡 Key 加 `--region intl`）。
- `HTTP 400` 提示音色不存在：音色名区分大小写，含空格的要加引号（`"Eldric Sage"`）。
- 返回的音频链接 24 小时有效，脚本已直接下载，不需要保留链接。
