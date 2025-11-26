# Chinese TTS Service with Mixed Language Support

This directory contains the Chinese TTS (Text-to-Speech) service based on [Kokoro-82M-v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh), with added support for mixed Chinese/English text synthesis.

## Features

- 🇨🇳 High-quality Chinese speech synthesis
- 🌐 **Mixed Language Support**: Automatically detects and synthesizes mixed Chinese/English text
- 🔄 Streaming audio output via RTP/UDP
- 📡 Real-time streaming to specified IP:port destinations
- 🎛️ Configurable voice, speed, codec, and chunk size

## Mixed Language Synthesis

The service now supports synthesizing text that contains both Chinese and English:

- Text is automatically split into language segments (Chinese vs English)
- Each segment is synthesized using the appropriate TTS model:
  - Chinese segments: Kokoro v1.1-zh model
  - English segments: Kokoro v1.0 model (downloaded automatically if needed)
- Audio is streamed continuously without gaps between segments

### How It Works

1. **Language Detection**: Text is analyzed character-by-character to identify ASCII (English) and non-ASCII (Chinese) segments
2. **Segment Synthesis**: Each segment is processed by the appropriate TTS model
3. **Streaming Output**: Audio chunks are yielded as they are generated, enabling real-time streaming

## API Usage

### RTP/UDP Streaming Endpoint

**Endpoint:** `POST /stream-rtp-streaming/`

Sends synthesized audio to a specified UDP destination in real-time.

**Request Body:**

```json
{
    "text": "Hello World 你好世界",
    "voice": "zf_001",
    "target_host": "192.168.1.100",
    "target_port": 5004,
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
| `text` | string | Yes | - | Text to synthesize (supports mixed Chinese/English) |
| `voice` | string | Yes | - | Chinese voice model (e.g., "zf_001") |
| `target_host` | string | Yes | - | Target IP address for UDP packets |
| `target_port` | int | Yes | - | Target UDP port |
| `speed` | float | No | 1.0 | Speech speed multiplier |
| `chunk_ms` | int | No | 20 | Milliseconds per RTP packet |
| `codec` | string | No | "pcmu" | Audio codec ("pcmu" for G.711 μ-law, "l16" for linear 16-bit) |
| `taskid` | string | No | auto | Task UUID for tracking/cancellation |
| `uuid_param` | string | No | null | Business UUID for grouping related tasks |
| `clear_msg` | bool | No | false | Clear pending tasks for uuid_param before queueing |

**Response:**

```json
{
    "status": "ok",
    "taskid": "550e8400-e29b-41d4-a716-446655440000",
    "uuid": "user-provided-uuid"
}
```

### Example Usage

**Mixed Chinese/English text:**

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "欢迎使用 TTS Service，这是一个 mixed language 示例。",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 5004,
       "speed": 1.0,
       "codec": "pcmu"
     }'
```

**Pure Chinese:**

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "你好，世界！",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 5004
     }'
```

**Pure English:**

```bash
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Hello, World!",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 5004
     }'
```

## Local Testing

### Using the UDP Sink Script

A helper script is provided to capture UDP audio for testing:

```bash
# Terminal 1: Start the UDP sink (listens on port 5004)
python scripts/local_udp_sink.py --port 5004 --output captured_audio.raw --strip-rtp-header

# Terminal 2: Send a TTS request
curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "Hello World 你好世界",
       "voice": "zf_001",
       "target_host": "127.0.0.1",
       "target_port": 5004,
       "codec": "pcmu"
     }'

# Convert captured audio to WAV (requires sox)
sox -t raw -r 8000 -c 1 -e mu-law captured_audio.raw output.wav
```

### UDP Sink Options

```
python scripts/local_udp_sink.py --help

Options:
  --port, -p        UDP port to listen on (default: 5004)
  --output, -o      Output file path (default: output.raw)
  --timeout, -t     Idle timeout in seconds (default: 30.0)
  --strip-rtp-header  Strip 12-byte RTP header from packets
  --verbose, -v     Print verbose packet information
```

## Voice Models

### Chinese Voices (v1.1-zh)

Available voices for Chinese synthesis:
- `zf_001` through `zf_050` - Female voices
- `zm_001` through `zm_050` - Male voices

See the full list at: https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/main/voices

### English Voice

The default English voice is `af_heart` from the v1.0 model. English model files are automatically downloaded when first needed.

## File Structure

```
src/chinese/
├── main.py              # FastAPI application with RTP streaming endpoint
├── lang_split.py        # Language detection and text segmentation
├── english_tts.py       # English TTS adapter
├── mixed_stream.py      # Mixed language stream composer
├── download_deps.py     # Model file downloader
├── cache.py             # Audio caching utilities
├── requirements.txt     # Python dependencies
├── Dockerfile           # Container configuration
├── docker-compose.yaml  # Docker compose configuration
├── models/              # Downloaded model files (auto-created)
└── voices/              # Voice configuration files
```

## Running the Service

### Local Development

```bash
cd src/chinese
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python main.py  # Runs on http://localhost:8210
```

### Docker

```bash
cd src/chinese
docker-compose up -d --build
```

## Troubleshooting

### English model not loading

If English text falls back to Chinese TTS, check the logs for model initialization errors. The English model files should be automatically downloaded to `models/`:
- `kokoro-v1.0.onnx`
- `voices-v1.0.bin`

### No audio received

1. Verify the target_host and target_port are correct
2. Check firewall settings for UDP traffic
3. Use the UDP sink script to test locally first
4. Check the application logs for streaming errors

### Audio quality issues

- Try different `chunk_ms` values (10, 20, 40ms)
- Switch between `pcmu` and `l16` codecs
- Adjust `speed` parameter for natural pacing
