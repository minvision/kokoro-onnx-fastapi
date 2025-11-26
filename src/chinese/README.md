# Chinese TTS Module with Mixed Language Support

This module provides Chinese text-to-speech functionality with support for mixed Chinese/English text.

## Features

- **Chinese TTS**: High-quality Chinese speech synthesis using Kokoro-82M-v1.1-zh model
- **Mixed Language Support**: Automatically detects and handles Chinese/English mixed text
- **RTP Streaming**: Real-time audio streaming via RTP/UDP protocol
- **Queue-based Processing**: Per-UUID job queues for sequential processing

## API Endpoints

### POST /stream-rtp-streaming/

Stream synthesized speech to a target IP:port via RTP/UDP.

**Request Body:**

```json
{
    "text": "你好，Hello World!",
    "voice": "zf_001",
    "target_host": "192.168.1.100",
    "target_port": 5000,
    "speed": 1.0,
    "chunk_ms": 20,
    "codec": "pcmu",
    "taskid": null,
    "uuid_param": null,
    "clear_msg": false
}
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| text | string | Yes | - | Text to synthesize (Chinese, English, or mixed) |
| voice | string | Yes | - | Chinese voice model (e.g., "zf_001") |
| target_host | string | Yes | - | Target IP address for RTP streaming |
| target_port | int | Yes | - | Target UDP port for RTP streaming |
| speed | float | No | 1.0 | Speech speed multiplier |
| chunk_ms | int | No | 20 | RTP packet duration in milliseconds |
| codec | string | No | "pcmu" | Audio codec ("pcmu" or "l16") |
| taskid | string | No | auto | Task ID for tracking (UUID format) |
| uuid_param | string | No | null | User UUID for queue management |
| clear_msg | bool | No | false | Clear pending tasks for uuid_param |

**Response:**

```json
{
    "status": "ok",
    "taskid": "abc123...",
    "uuid": "user-uuid-if-provided"
}
```

## Mixed Language Support

The module automatically segments mixed Chinese/English text and routes each segment to the appropriate TTS model:

- **Chinese segments**: Processed by the Chinese Kokoro model (v1.1-zh)
- **English segments**: Processed by the English Kokoro model (v1.0) if available, otherwise falls back to Chinese model

### Example Mixed Text

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
         "text": "你好，Welcome to China! 这是一个混合语言的例子。",
         "voice": "zf_001",
         "target_host": "127.0.0.1",
         "target_port": 5000
     }'
```

## Local Testing

### Using the UDP Sink Tool

A test tool is provided for receiving and saving RTP audio data:

```bash
# Start the UDP sink (listens on port 5000)
cd scripts
python local_udp_sink.py --port 5000 --output received.pcm

# In another terminal, send TTS request
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{"text": "测试语音", "voice": "zf_001", "target_host": "127.0.0.1", "target_port": 5000}'

# Convert received PCM to WAV (PCMU codec at 8kHz)
ffmpeg -f mulaw -ar 8000 -ac 1 -i received.pcm received.wav
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
cd /path/to/kokoro-onnx-fastapi
pytest tests/test_mixed_stream.py -v
```

## Architecture

```
src/chinese/
├── main.py           # FastAPI application and endpoints
├── lang_split.py     # Language detection and text segmentation
├── english_tts.py    # English TTS adapter (uses src/other model)
├── mixed_stream.py   # Mixed language stream generator
├── cache.py          # Audio file caching
└── download_deps.py  # Model dependency management
```

## Voice Models

### Chinese Voices (v1.1-zh)

Available voices can be found in the `voices/` directory or at:
https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices

### English Voices (v1.0)

When English support is enabled, the following voices are available:
https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md

Default English voice: `af_heart`

## Requirements

See `requirements.txt` for full dependencies. Key packages:

- `kokoro-onnx`: TTS model inference
- `misaki`: G2P (grapheme-to-phoneme) conversion
- `fastapi`: Web framework
- `uvicorn`: ASGI server

## Error Handling

- If the English TTS model is not available, English text segments will be processed by the Chinese model
- Network errors during RTP streaming are logged but do not fail the HTTP request
- Invalid task IDs return HTTP 400/409 errors
