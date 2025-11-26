# kokoro-onnx-fastapi

*[English](README.en.md) | [简体中文](README.md)*

A lightweight text-to-speech API service based on [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx), built with the FastAPI framework. This project provides an easy-to-use local or server-based speech synthesis solution, supporting high-quality voice generation for Chinese and other languages (such as English).

## Features

- 🚀 High-performance FastAPI interface with quick response
- 🐳 Full Docker containerization support
- 🌏 Separate deployment for Chinese and other language models (located in src/chinese and src/other directories)
- 🔀 **Support for mixed Chinese-English input in streaming TTS audio generation**
- 📦 Automatic dependency download and management on first startup
- 💾 Audio file caching to improve response speed for repeated requests
- 🔄 Speech speed adjustment support
- 🧩 Rich variety of voice models to choose from

**Explanation of Chinese and Other Language Model Separation:**  
The Chinese voice model [Kokoro-82M-v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) and other language models [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) are independent projects with different model structures and voice characteristics. This project implements directory isolation to allow independent deployment and on-demand use of both model sets, avoiding unnecessary resource consumption.

## System Requirements

- Python 3.12 or higher
- [uv package manager](https://docs.astral.sh/uv/getting-started/installation) (recommended)
- Approximately 1GB disk space for storing model files
- Docker and docker-compose (for containerized deployment)

## Quick Start

### Local Deployment

```console
# Clone the repository
git clone https://github.com/kamjin3086/kokoro-onnx-fastapi.git

# Chinese service
cd kokoro-onnx-fastapi/src/chinese
uv venv -p 3.12 && source .venv/bin/activate  # Linux/macOS
# or .venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
python main.py  # Service runs on http://localhost:8210

# Other language service
cd kokoro-onnx-fastapi/src/other
uv venv -p 3.12 && source .venv/bin/activate  # Linux/macOS
# or .venv\Scripts\activate  # Windows
uv pip install -r requirements.txt
python main.py  # Service runs on http://localhost:8211
```

### Docker Container Deployment

```console
# Chinese service
cd kokoro-onnx-fastapi/src/chinese
docker-compose up -d --build  # Service runs on http://localhost:8210

# Other language service
cd kokoro-onnx-fastapi/src/other
docker-compose up -d --build  # Service runs on http://localhost:8211
```

## API Usage Guide

API documentation is available at: `http://localhost:8210/docs` (Chinese service) or `http://localhost:8211/docs` (Other language service)

### Usage Examples

**Chinese Speech Synthesis:**

```console
curl -X POST "http://localhost:8210/generate-speech/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，世界！", "voice":"zf_001", "filename":"hello_world", "speed": 1.0}' \
     --output hello_world.wav
```

**Other Language (e.g., English) Speech Synthesis:**

```console
curl -X POST "http://localhost:8211/generate-speech/" \
     -H "Content-Type: application/json" \
     -d '{"text":"Hello world, this is a test.", "voice":"af_heart", "filename":"hello_test", "speed": 1.0}' \
     --output hello_test.wav
```

**Mixed Chinese-English Streaming Speech Synthesis (RTP Stream):**

The Chinese service (port 8210) supports mixed Chinese-English input, automatically detecting Chinese and English segments in the text, generating audio using the corresponding voice models, and streaming via RTP.

```console
curl -X POST "http://localhost:8210/stream-rtp-streaming-mixed/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "你好，Welcome to 北京！This is a test of mixed language streaming.",
       "voice_zh": "zf_001",
       "voice_en": "af_heart",
       "target_host": "192.168.1.100",
       "target_port": 5004,
       "speed": 1.0
     }'
```

| Parameter | Description |
|-----------|-------------|
| text | Text content to be converted (supports mixed Chinese-English) |
| voice_zh | Chinese voice model name, e.g., "zf_001" |
| voice_en | English voice model name, e.g., "af_heart" |
| target_host | RTP stream target IP address |
| target_port | RTP stream target UDP port |
| speed | (Optional) Speech speed adjustment, default is 1.0 |

| Parameter | Description |
|-----------|-------------|
| text | Text content to be converted to speech |
| voice | Voice model name, e.g., "zf_001" (Chinese) or "af_heart" (English) |
| filename | (Optional) Filename for the generated audio, without path and extension |
| speed | (Optional) Speech speed adjustment, default is 1.0 |

## Configuration and Customization

- Model files are automatically downloaded and saved to the `models/` folder in each service directory
- Generated audio files are stored in the `generated_audio/` folder in each service directory
- Service parameters can be adjusted by editing the `main.py` configuration file


## Voice Model Information

- **Chinese Voice Models**: Uses the `v1.1-zh` version model, providing various Chinese female and male voices. [View detailed list](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices)
- **Other Language Voice Models**: Uses the `v1.0` version model, supporting various languages and voice types. [View detailed list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

## License

This project is licensed under the [MIT License](LICENSE), based on the [original kokoro-onnx project](https://github.com/thewh1teagle/kokoro-onnx). Please also follow the licensing requirements of the original project. 