# Chinese TTS Module with Mixed Language Support

This module provides Chinese text-to-speech (TTS) synthesis with support for mixed Chinese and English text. Audio is streamed via RTP/UDP protocol for real-time applications.

## Features

- **Chinese TTS**: High-quality Chinese voice synthesis using Kokoro v1.1-zh model
- **Mixed Language Support**: Automatic detection and handling of Chinese/English text segments
- **Streaming Output**: Real-time audio streaming via RTP/UDP protocol
- **Task Queue Management**: Per-user task queuing with cancellation support
- **Persistent RTP Context**: Maintains SSRC/sequence/timestamp continuity across multiple requests

## Installation

```bash
cd src/chinese
uv venv -p 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
```

For English TTS support, also install the English model:
```bash
cd src/other
uv venv -p 3.12 && source .venv/bin/activate
uv pip install -r requirements.txt
python download_deps.py  # Download English model files
```

## Running the Service

```bash
python main.py  # Runs on http://localhost:8210
```

Or with Docker:
```bash
docker-compose up -d --build
```

## API Endpoints

### POST /stream-rtp-streaming/

Stream synthesized speech via RTP/UDP protocol.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `text` | string | Yes | - | Text to synthesize (supports mixed Chinese/English) |
| `voice` | string | Yes | - | Chinese voice name (e.g., 'zf_001') |
| `target_host` | string | Yes | - | Target IP address for RTP packets |
| `target_port` | int | Yes | - | Target UDP port for RTP packets |
| `speed` | float | No | 1.0 | Speech speed multiplier |
| `chunk_ms` | int | No | 20 | Milliseconds per RTP packet |
| `ssrc` | int | No | random | RTP SSRC identifier |
| `codec` | string | No | "pcmu" | Audio codec: "pcmu" or "l16" |
| `taskid` | string | No | auto | Task ID (UUID) for tracking |
| `uuid_param` | string | No | - | Business UUID for grouping tasks |
| `clear_msg` | bool | No | false | Clear pending tasks for this UUID |
| `voice_en` | string | No | "af_heart" | English voice name |

**Example - Mixed Chinese/English:**

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "你好，Hello World！这是中英混合测试。",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 5004
     }'
```

**Response:**
```json
{
  "status": "ok",
  "taskid": "uuid-string",
  "uuid": null
}
```

### POST /stream-cancel/{taskid}

Cancel a running or queued task by task ID.

### POST /stream-cancel-by-uuid/{user_uuid}

Cancel all tasks associated with a business UUID.

### GET /stream-status/{taskid}

Query the status of a task.

## Local Testing

### Step 1: Start the UDP Listener

Use the provided script to receive and save RTP audio:

```bash
python scripts/local_udp_sink.py --port 5004 --output received_audio.raw
```

### Step 2: Send a Request

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "你好世界，Hello World！",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 5004,
       "codec": "pcmu"
     }'
```

### Step 3: Play the Audio

```bash
# For PCMU codec:
ffplay -f mulaw -ar 8000 -ac 1 received_audio.raw

# For L16 codec:
ffplay -f s16le -ar 8000 -ac 1 received_audio.raw
```

## How Mixed Language Detection Works

The system splits input text into segments based on character type:
- **Chinese segments**: Non-ASCII characters (Chinese characters, CJK punctuation)
- **English segments**: ASCII characters (English letters, numbers, ASCII punctuation)

Short English segments (like single punctuation marks) are automatically merged with adjacent Chinese segments to reduce frequent TTS engine switching.

**Example:**
```
Input: "你好，Hello World！这是测试。"
Segments:
  1. (zh) "你好，"
  2. (en) "Hello World"
  3. (zh) "！这是测试。"
```

## Available Voices

### Chinese Voices (v1.1-zh model)
See: https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices

Common voices: `zf_001`, `zf_002`, `zm_001`, etc.

### English Voices (v1.0 model)
See: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

Common voices: `af_heart`, `af_bella`, `am_adam`, etc.

## Known Limitations

1. **ASCII-based segmentation**: Language detection is based on character code ranges, not actual language identification. Some edge cases may be mis-classified.

2. **No cross-language voice consistency**: Chinese and English segments use different voice models, so voice characteristics may vary between segments.

3. **Model loading time**: English model is loaded lazily on first use, which may cause a slight delay on the first mixed-language request.

4. **Sample rate differences**: The system handles sample rate conversion automatically, but some audio quality degradation may occur when converting between different sample rates.

## Architecture

```
src/chinese/
├── main.py              # FastAPI application and endpoints
├── lang_split.py        # Language segmentation logic
├── english_tts.py       # English TTS wrapper (uses src/other model)
├── mixed_stream.py      # Mixed language streaming orchestrator
├── download_deps.py     # Chinese model dependency downloader
├── cache.py             # Audio caching utilities
└── requirements.txt     # Python dependencies

src/other/
├── main.py              # English TTS standalone service (for model files)
├── download_deps.py     # English model dependency downloader
└── models/              # English model files (auto-downloaded)

src/utils/
└── stream_rtp_streaming.py  # RTP/UDP streaming utilities

scripts/
└── local_udp_sink.py    # UDP listener for testing

tests/
└── test_mixed_stream.py # Unit tests for mixed language streaming
```

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/test_mixed_stream.py -v
```
