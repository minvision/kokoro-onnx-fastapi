# Chinese TTS Module with Mixed Language Support

This module provides Chinese text-to-speech functionality with support for mixed Chinese/English text. It uses the Kokoro TTS model for speech synthesis and supports real-time RTP/UDP audio streaming.

## Features

- **Chinese TTS**: High-quality Chinese speech synthesis using Kokoro-82M-v1.1-zh model
- **Mixed Language Support**: Automatic detection and handling of mixed Chinese/English text
- **RTP/UDP Streaming**: Real-time audio streaming via RTP/UDP protocol
- **Queue-based Processing**: Per-UUID task queues for sequential processing
- **Task Management**: Support for task cancellation and status tracking

## Quick Start

### Prerequisites

- Python 3.12+
- [uv package manager](https://docs.astral.sh/uv/getting-started/installation) (recommended)

### Installation

```bash
cd src/chinese
uv venv -p 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
```

### Running the Service

```bash
python main.py
# Service runs on http://localhost:8210
```

## API Endpoints

### POST /stream-rtp-streaming/

Stream synthesized speech via RTP/UDP to a specified target.

**Request Body:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `text` | string | Yes | Text to synthesize (supports Chinese, English, or mixed) |
| `voice` | string | Yes | Voice model name (e.g., 'zf_001' for Chinese) |
| `target_host` | string | Yes | Target IP address for RTP/UDP streaming |
| `target_port` | int | Yes | Target UDP port |
| `speed` | float | No | Speech speed (default: 1.0) |
| `chunk_ms` | int | No | RTP packet duration in ms (default: 20) |
| `ssrc` | int | No | RTP SSRC identifier (auto-generated if not provided) |
| `codec` | string | No | Audio codec: 'pcmu' or 'l16' (default: 'pcmu') |
| `taskid` | string | No | Task UUID (auto-generated if not provided) |
| `uuid_param` | string | No | Business UUID for task grouping |
| `clear_msg` | bool | No | Clear pending tasks for uuid_param before enqueuing (default: false) |

**Example - Chinese Text:**

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好世界",
    "voice": "zf_001",
    "target_host": "127.0.0.1",
    "target_port": 5000,
    "speed": 1.0,
    "codec": "pcmu"
  }'
```

**Example - Mixed Chinese/English Text:**

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好Hello世界World",
    "voice": "zf_001",
    "target_host": "127.0.0.1",
    "target_port": 5000,
    "speed": 1.0
  }'
```

**Response:**

```json
{
  "status": "ok",
  "taskid": "uuid-string",
  "uuid": "user-uuid-if-provided"
}
```

### POST /stream-cancel/{taskid}

Cancel a specific streaming task.

### POST /stream-cancel-by-uuid/{user_uuid}

Cancel all tasks associated with a user UUID.

### GET /stream-status/{taskid}

Get the status of a specific task.

## Mixed Language Processing

When you send mixed Chinese/English text, the system automatically:

1. **Detects language segments**: Splits text into Chinese and English portions
2. **Routes to appropriate TTS engine**: 
   - Chinese text → Chinese Kokoro model (Kokoro-82M-v1.1-zh)
   - English text → English Kokoro model (Kokoro-82M v1.0)
3. **Concatenates audio streams**: Merges the audio outputs sequentially

### Language Detection

The system uses character-based detection:
- ASCII characters (0x00-0x7F) → English
- Non-ASCII characters → Chinese

Short English segments (e.g., punctuation, single digits) surrounded by Chinese text may be merged with the Chinese portions to avoid frequent engine switching.

## Local Testing

### Using the UDP Sink

For local testing, you can use the provided UDP sink script to receive and save audio:

```bash
# Terminal 1: Start the UDP sink
python scripts/local_udp_sink.py --port 5000 --output /tmp/audio.raw

# Terminal 2: Start the TTS service
cd src/chinese
python main.py

# Terminal 3: Send a request
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello你好World世界",
    "voice": "zf_001",
    "target_host": "127.0.0.1",
    "target_port": 5000
  }'
```

### Converting Raw Audio to WAV

For PCMU (G.711 μ-law) audio:
```bash
ffmpeg -f mulaw -ar 8000 -ac 1 -i /tmp/audio.raw /tmp/audio.wav
```

For L16 (Linear 16-bit PCM) audio:
```bash
ffmpeg -f s16le -ar 8000 -ac 1 -i /tmp/audio.raw /tmp/audio.wav
```

## Architecture

```
src/chinese/
├── main.py              # FastAPI application and endpoints
├── lang_split.py        # Language detection and text splitting
├── english_tts.py       # English TTS adapter (uses src/other/main)
├── mixed_stream.py      # Mixed language stream synthesizer
├── cache.py             # Audio caching utilities
├── download_deps.py     # Dependency management
└── models/              # Downloaded model files
```

## Dependencies

The mixed language feature requires both Chinese and English Kokoro models:

- **Chinese Model**: `kokoro-v1.1-zh.onnx`, `voices-v1.1-zh.bin`
- **English Model**: `kokoro-v1.0.onnx`, `voices-v1.0.bin` (from src/other)

Models are automatically downloaded on first startup.

## Voice Options

### Chinese Voices
See [Kokoro-82M-v1.1-zh voices](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices)

Common options:
- `zf_001` - Female voice
- `zm_001` - Male voice

### English Voices (for mixed text)
See [Kokoro-82M VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)

Default English voice: `af_heart`

## Troubleshooting

### Model Not Loaded

If you see "模型服务尚未准备好" error:
1. Check that model files exist in `src/chinese/models/`
2. Verify sufficient disk space for model download
3. Check application logs for download errors

### Mixed Language Not Working

If English portions are not being synthesized:
1. Ensure the English model service (src/other) has been initialized
2. Check that `src/other/main.py` kokoro_model is loaded
3. Review logs for English TTS adapter errors

### UDP Streaming Issues

If audio is not being received:
1. Verify firewall allows UDP traffic on the target port
2. Check that target_host and target_port are correct
3. Use the local UDP sink for testing
