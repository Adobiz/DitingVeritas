# 谛听·译真 DitingVeritas

一个轻量，极简，好用的 AI 同声传译助手 — 系统音频实时捕获 → VAD 切句 → ASR 识别 → LLM 翻译 → 悬浮字幕呈现

<img src="assets/screenshot.png" alt="DitingVeritas" width="600" /> 

## Video

[![Install & Demo](https://img.shields.io/badge/Bilibili-Install%20%26%20Demo-00A1D6?logo=bilibili)](https://www.bilibili.com/video/BV1orE86hEto/)

## 快速开始
Release下载exe安装包，双击下载相关前置模型即可使用(经测试好像部分情况存在bug，建议使用常规开始测试)
## 常规开始
```bash
# 1. 安装后端依赖
cd backend
pip install -r requirements.txt

# 2. 配置 API Key（可选，也可在前端设置面板填）
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 等

# 3. 启动（前后端自动）
cd frontend
npm install
npm run electron:build
然后在release/win-unpacked/DitingVeritas.exe 运行测试
```

双击悬浮球「谛」→ ⚙ 设置 → 选择模型 → ▶ 开始 → 播放英文音频即可。

## 一键打包启动

```bash
build.bat
```
自动生成 DitingVeritas/frontend/release/win-unpacked/DitingVeritas.exe
双击打开即可运行

## 功能

| 模块 | 功能 |
|------|------|
| 🎤 音频捕获 | WASAPI Loopback 系统音频，自动检测设备 |
| 🔍 VAD | silero-vad 流式语音检测，采样点索引 |
| 🗣 ASR | faster-whisper tiny/small，支持 11 语种 |
| 🚀 GPU 加速 | CUDA float16 / CPU int8 一键切换 |
| 🌐 翻译引擎 | Claude + DeepSeek/OpenAI 兼容 + 本地 NLLB-200 |
| ⚡ 三模式 | 强化(turbo) / 均衡(balanced) / 稳定(stable) |
| 📡 闻境 | URL 抓取→关键词提取→术语注入翻译 |
| 🔄 谛听辨伪 | LLM 校对回溯，自动修正前文翻译错误 |
| 🎨 主题 | 8 色 HSL 暗黑玻璃 + 透明度/亮度调节 |
| 🌍 多语言 | 11 语种前端选择，动态同步 ASR/翻译 prompt |
| 💻 一键启动 | Electron 自动拉起后端，双击即用 |

## 项目结构

```
DitingVeritas/
├── backend/
│   ├── config.py                  # 7 个配置 dataclass
│   ├── main.py                    # FastAPI + WebSocket + 管道
│   ├── requirements.txt
│   ├── models/
│   │   └── schemas.py             # 消息协议
│   └── pipeline/
│       ├── audio_capture.py       # WASAPI Loopback
│       ├── vad.py                 # silero-vad
│       ├── asr.py                 # faster-whisper
│       ├── translator.py          # Claude + OpenAI + 本地
│       ├── local_translator.py    # CTranslate2 NLLB
│       ├── context_loader.py      # 闻境 URL 抓取
│       ├── corrector.py           # 谛听辨伪
│       ├── incremental.py         # 增量 ASR 处理
│       └── modes.py               # 三模式参数
├── frontend/
│   ├── electron/
│   │   ├── main.cjs               # Electron 主进程（自动启动后端）
│   │   └── preload.cjs
│   └── src/
│       ├── App.tsx                # 控制球 + 设置面板
│       ├── colors.ts              # HSL 色彩引擎
│       ├── components/
│       │   └── SubtitleOverlay.tsx
│       └── hooks/
│           └── useWebSocket.ts
├── build.bat                      # 一键构建 EXE
└── README.md
```

## WebSocket 协议

```
客户端 → 服务端: start | stop | context_update
服务端 → 客户端: translation | correction | status | error | context_ready
```

## 本地模型
faster-whisper 首次运行自动下载，这边也提供手动下载链接

官网：

https://huggingface.co/Systran/faster-whisper-tiny

https://huggingface.co/Systran/faster-whisper-small

镜像：

https://hf-mirror.com/Systran/faster-whisper-tiny

https://hf-mirror.com/Systran/faster-whisper-small

支持 CTranslate2 格式的 NLLB-200 int8 量化模型：

1. 下载模型到本地目录
2. 前端 ⚙ → 添加模型 → 名称 NLLB → API Key 留空 → 本地路径填模型目录
3. 选择该模型 → ▶ 启动

#### 这边提供夸克网盘下载链接

我用夸克网盘分享了「NLLB-200」，点击链接即可保存。打开「夸克APP」。
链接：https://pan.quark.cn/s/1163d697431f
提取码：6Wuq

## 环境变量 (.env)

```
TRANSLATOR_PROVIDER=openai        # claude | openai | auto
TRANSLATOR_MODEL=deepseek-chat
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.deepseek.com
ANTHROPIC_API_KEY=sk-ant-xxx
PIPELINE_MODE=balanced            # turbo | balanced | stable
```

## License

MIT
