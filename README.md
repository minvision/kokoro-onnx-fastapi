# kokoro-onnx-fastapi

*[简体中文](README.md) | [English](README.en.md)*

基于[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)开发的轻量级语音合成API服务，采用FastAPI框架构建。本项目提供简便易用的本地或服务器语音合成解决方案，支持中文及其他语言（如英文）的高质量语音生成。

## 项目特点

- 🚀 高性能FastAPI接口，响应迅速
- 🐳 完整支持Docker容器化部署
- 🌏 中文和其他语言模型分离部署（位于src/chinese和src/other目录）
- 🔀 **中英文混合文本支持**：自动识别并分段处理中英文混合文本
- 📦 首次启动自动下载并管理依赖资源
- 💾 支持音频文件缓存，提高重复请求响应速度
- 🔄 支持语音生成速度调节
- 🧩 丰富多样的声音模型选择
- 📡 支持RTP/UDP流式音频发送

**中文与其他语言模型分离说明：**  
中文语音模型[Kokoro-82M-v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)与其他语言模型[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)是两个独立的项目，拥有不同的模型结构和语音特性。本项目通过目录隔离实现两套模型的独立部署与按需使用，避免不必要的资源占用。

## 系统要求

- Python 3.12或更高版本
- [uv包管理工具](https://docs.astral.sh/uv/getting-started/installation)（推荐使用）
- 约1GB磁盘空间用于存储模型文件
- Docker与docker-compose（如需容器化部署）

## 快速开始

### 本地运行

```console
# 克隆代码仓库
git clone https://github.com/kamjin3086/kokoro-onnx-fastapi.git

# 中文服务
cd kokoro-onnx-fastapi/src/chinese
uv venv -p 3.12 && source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
python main.py  # 服务运行在 http://localhost:8210

# 其他语言服务
cd kokoro-onnx-fastapi/src/other
uv venv -p 3.12 && source .venv/bin/activate  # Linux/macOS
# 或 .venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
python main.py  # 服务运行在 http://localhost:8211
```

### Docker容器部署

```console
# 中文服务
cd kokoro-onnx-fastapi/src/chinese
docker-compose up -d --build  # 服务运行在 http://localhost:8210

# 其他语言服务
cd kokoro-onnx-fastapi/src/other
docker-compose up -d --build  # 服务运行在 http://localhost:8211
```

## API使用指南

API接口文档访问地址：`http://localhost:8210/docs`（中文服务）或`http://localhost:8211/docs`（其他语言服务）

### 使用示例

**中文语音合成：**

```console
curl -X POST "http://localhost:8210/generate-speech/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，世界！", "voice":"zf_001", "filename":"hello_world", "speed": 1.0}' \
     --output hello_world.wav
```

**其他语言（如英文）语音合成：**

```console
curl -X POST "http://localhost:8211/generate-speech/" \
     -H "Content-Type: application/json" \
     -d '{"text":"Hello world, this is a test.", "voice":"af_heart", "filename":"hello_test", "speed": 1.0}' \
     --output hello_test.wav
```

| 参数 | 说明 |
|------|------|
| text | 要转换的文本内容 |
| voice | 声音模型名称，如"zf_001"(中文)或"af_heart"(英文) |
| filename | (可选)生成的音频文件名，不含路径和扩展名 |
| speed | (可选)语音速度调节，默认为1.0 |

### 中英文混合文本支持

中文服务（src/chinese）现已支持中英文混合文本的语音合成。系统会自动：

1. 识别文本中的中文和英文部分
2. 使用相应的TTS模型处理各语言段落
3. 按顺序流式输出合成后的音频

**RTP流式发送示例（中英混合）：**

```console
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "你好，Hello World，欢迎使用语音合成服务！",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 9000,
       "en_voice": "af_heart",
       "speed": 1.0
     }'
```

| 参数 | 说明 |
|------|------|
| text | 要转换的文本内容（支持中英文混合） |
| voice | 中文声音模型名称，如"zf_001" |
| target_host | 接收RTP的目标IP地址 |
| target_port | 接收RTP的目标UDP端口 |
| en_voice | (可选)英文声音模型名称，如"af_heart"，默认使用af_heart |
| speed | (可选)语音速度调节，默认为1.0 |
| codec | (可选)编码格式，'pcmu'或'l16'，默认为'pcmu' |
| chunk_ms | (可选)每个RTP包的毫秒数，默认20ms |

### 本地测试

使用提供的UDP接收脚本测试RTP流：

```console
# 终端1：启动UDP接收器
python scripts/local_udp_sink.py --port 9000 --output /tmp/received_audio.pcm

# 终端2：发送TTS请求
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "测试中英混合：Hello World！",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 9000
     }'

# 播放接收到的音频（PCMU格式）
aplay -f MU_LAW -r 8000 -c 1 /tmp/received_audio.pcm
```

## 配置与自定义

- 模型文件自动下载并保存至各自服务目录下的`models/`文件夹
- 生成的音频文件存储在各自服务目录下的`generated_audio/`文件夹
- 可通过编辑`main.py`配置文件调整服务参数


## 声音模型说明

- **中文声音模型**: 使用`v1.1-zh`版本模型，提供多种中文女声和男声选择。[查看详细列表](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices)
- **其他语言声音模型**: 使用`v1.0`版本模型，支持多种语言和声音类型。[查看详细列表](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

## 已知限制

- 中英文混合分段基于ASCII/非ASCII字符范围判断，可能对某些特殊场景（如带音标的拼音）效果不佳
- 英文模型（v1.0）需要单独下载，首次使用中英混合功能时会自动下载
- 如果英文模型不可用，系统会自动回退到使用中文模型处理英文部分

## 许可证

本项目采用[MIT许可证](LICENSE)，基于[原kokoro-onnx项目](https://github.com/thewh1teagle/kokoro-onnx)开发，请同时遵循原项目的许可要求。 