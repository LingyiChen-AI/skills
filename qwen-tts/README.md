# qwen-tts

用阿里云百炼 Qwen-Audio 做中文配音、声音复刻和配乐。给视频配旁白时一句一个文件，
输出 manifest 记录每段时长，方便画面和字幕按真实时长对齐。

## 依赖

- Python 3.8+，脚本只用标准库。
- `ffmpeg`：mp3/m4a 输出、`--speed` 变速、`music --loop-to` 循环要用（Windows `winget install Gyan.FFmpeg`，macOS `brew install ffmpeg`）。

## 配置

```bash
export DASHSCOPE_API_KEY=<百炼 API Key>      # Windows: setx DASHSCOPE_API_KEY <Key>
```

Key 在 https://bailian.console.aliyun.com/ 创建。新加坡地域的 Key 加 `--region intl`。

## 命令

| 命令 | 用途 |
| --- | --- |
| `say` | 合成一段（长文本自动切块拼接） |
| `batch` | 多段旁白，每段一个文件 + `manifest.json`（start / seconds） |
| `clone` | 样音 wav 复刻成固定音色，得到可直接当 `--voice` 用的 voice_id |
| `music` | 按文字描述生成配乐 / 音效（`qwen-audio-3.1-tts-next`），可交叉淡化循环到指定长度 |
| `voices` | 列出音色 |

默认模型 `qwen-audio-3.1-tts-flash`，默认音色 `anmingyuan_v3.1`，支持 `--instructions` 用自然语言控制语气。

## 几个实测出来的点

- `qwen-audio-3.1-tts-next` 能按描述生成很像真人的声音，但每次调用音色都不一样，整片配音会一句一个人。
  做法是先用它生成几段样音挑一个，`clone` 复刻成 flash 的固定音色，再逐句合成。
- tts-next 生成音乐的字段是 `input.text_prompt`，不是 `text`（官方文档没写）。
- 流式返回的 WAV 头里长度是占位值，直接读时长会是 0，脚本已按实际数据重写 WAV 头。
- 字幕要和口播严格对齐时，一句一段合成，字幕用原文，不要整篇合成后按字数估算。
