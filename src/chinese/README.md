# Chinese TTS Service with Mixed Language Support

中文语音合成服务，支持中英混合文本。

## 功能特点

- 🇨🇳 **中文语音合成**: 使用 Kokoro v1.1-zh 模型
- 🇬🇧 **英文语音合成**: 使用 Kokoro v1.0 模型
- 🔀 **中英混合**: 自动识别文本中的中英文片段，分别合成后拼接
- 📡 **流式输出**: 支持 StreamingResponse 实时返回音频
- 🔌 **Socket 推送**: 可同时将音频流发送到指定 IP:port（UDP/TCP）
- 🎯 **兼容现有接口**: 保持与原有 `/stream-rtp-streaming/` 接口的兼容性

## 新增接口

### POST /synthesize/

中英混合文本语音合成接口。

**请求参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| text | string | ✓ | - | 要合成的文本（支持中文、英文或混合） |
| voice | string | ✗ | zf_001 | 中文声音模型名称 |
| english_voice | string | ✗ | af_heart | 英文声音模型名称 |
| speed | float | ✗ | 1.0 | 语速调节 |
| ip | string | ✗ | - | 接收音频流的目标 IP 地址 |
| port | int | ✗ | - | 接收音频流的目标端口 |
| protocol | string | ✗ | udp | 发送协议: "udp" 或 "tcp" |
| sample_rate | int | ✗ | 24000 | 输出采样率 |

**返回：**

- Content-Type: `audio/pcm`
- 响应头包含：
  - `X-Sample-Rate`: 采样率
  - `X-Channels`: 声道数 (1=mono)
  - `X-Bits-Per-Sample`: 位深 (16)
  - `X-Language-Mix`: 是否为混合语言文本

**使用示例：**

```bash
# 纯中文
curl -X POST "http://localhost:8210/synthesize/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，世界"}' \
     --output chinese.pcm

# 纯英文
curl -X POST "http://localhost:8210/synthesize/" \
     -H "Content-Type: application/json" \
     -d '{"text":"Hello, world", "voice":"zf_001", "english_voice":"af_heart"}' \
     --output english.pcm

# 中英混合
curl -X POST "http://localhost:8210/synthesize/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，hello world，欢迎使用 TTS 服务"}' \
     --output mixed.pcm

# 带 Socket 推送
curl -X POST "http://localhost:8210/synthesize/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，hello", "ip":"192.168.1.100", "port":5200, "protocol":"udp"}' \
     --output output.pcm
```

### POST /analyze-text/

分析文本的语言组成。

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| text | string | ✓ | 要分析的文本 |

**返回示例：**

```json
{
    "analysis": {
        "has_chinese": true,
        "has_english": true,
        "is_mixed": true,
        "segment_count": 4,
        "chinese_ratio": 0.6,
        "english_ratio": 0.4
    },
    "segments": [
        {"text": "你好，", "language": "zh"},
        {"text": "hello world", "language": "en"},
        {"text": "，世界", "language": "zh"}
    ],
    "total_length": 20
}
```

## 本地测试

### 1. 启动 UDP 接收器（可选）

如需测试 Socket 推送功能，先启动接收器：

```bash
# 在一个终端中
cd kokoro-onnx-fastapi
python scripts/local_udp_sink.py --port 5200 --output received_audio.pcm
```

### 2. 启动 TTS 服务

```bash
cd src/chinese
uv venv -p 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
python main.py
```

### 3. 测试请求

```bash
# 测试带 Socket 推送的请求
curl -X POST "http://localhost:8210/synthesize/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，this is a test，谢谢", "ip":"127.0.0.1", "port":5200}' \
     --output http_output.pcm
```

### 4. 播放 PCM 音频

```bash
# 使用 ffplay
ffplay -f s16le -ar 24000 -ac 1 received_audio.pcm

# 或转换为 WAV
sox -r 24000 -c 1 -b 16 -e signed-integer received_audio.pcm output.wav
```

## 运行测试

```bash
cd kokoro-onnx-fastapi
pip install pytest pytest-asyncio numpy
pytest tests/test_mixed_tts.py -v
```

## 声音模型

### 中文声音（v1.1-zh）

- `zf_001` - `zf_050`: 中文女声
- `zm_001` - `zm_050`: 中文男声

详见: https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices

### 英文声音（v1.0）

- `af_heart`, `af_nicole`, `af_sky` 等: 美式女声
- `am_adam`, `am_michael`: 美式男声
- `bf_emma`, `bf_isabella`: 英式女声
- `bm_george`, `bm_lewis`: 英式男声

详见: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

## 文件结构

```
src/chinese/
├── main.py           # FastAPI 主程序
├── mixed_tts.py      # 中英混合 TTS 逻辑
├── english_tts.py    # 英文 TTS 模块
├── stream_sender.py  # UDP/TCP 音频发送器
├── utils.py          # 工具函数（语言分段、音频处理）
├── download_deps.py  # 模型依赖下载
├── cache.py          # 音频缓存
├── requirements.txt  # Python 依赖
└── models/           # 模型文件目录（自动下载）
    ├── kokoro-v1.1-zh.onnx
    ├── voices-v1.1-zh.bin
    ├── config.json
    ├── kokoro-v1.0.onnx      # 英文模型（混合TTS需要）
    └── voices-v1.0.bin        # 英文声音（混合TTS需要）
```

## 技术说明

### 语言分段策略

使用简单的 ASCII/非ASCII 字符边界进行分段：
- ASCII 字符（0x00-0x7F）: 视为英文
- 非 ASCII 字符: 视为中文

这种方式无需额外依赖，适用于大多数中英混合场景。

### 音频格式

- 输出格式: 16-bit PCM, 单声道, Little-endian
- 默认采样率: 24000 Hz
- 支持的采样率: 8000, 16000, 22050, 24000, 44100, 48000

### 错误处理

- Socket 发送失败不会中断 HTTP 响应
- 英文模型加载失败时，会回退到使用中文模型处理英文文本
- 各种错误通过日志记录，不影响主流程

## 已知限制

1. 语言分段基于字符，对于混合词（如 "iPhone手机"）可能分段不理想
2. 中英文模型的声音特征不同，混合输出可能有明显的声音切换
3. 首次使用英文功能时会自动下载英文模型（约 200MB）

## 未来改进

- [ ] 支持更精细的语言检测（可选接入 langdetect）
- [ ] 添加交叉淡入淡出以平滑语言切换
- [ ] 支持更多语言的混合
- [ ] 添加音频缓存以加速重复请求
