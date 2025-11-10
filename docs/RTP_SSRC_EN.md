# RTP SSRC Explanation for Voice Transmission

## What is SSRC?

**SSRC (Synchronization Source)** is a 32-bit field in the RTP (Real-time Transport Protocol) header that serves as a synchronization source identifier.

## Purpose and Meaning of SSRC

SSRC is used to **uniquely identify a media stream source** within an RTP session. Its main purposes include:

1. **Stream Identification**: Distinguishes different media sources (e.g., audio streams from multiple participants) within the same RTP session
2. **Synchronization Reference**: Enables receivers to identify all packets belonging to the same source
3. **Collision Detection**: When an SSRC collision is detected, the sender must change its SSRC value
4. **Stream Binding**: Associates RTP data streams with RTCP reports

## Does SSRC Increment Per Packet?

**No, the SSRC value remains constant throughout the entire stream transmission and does not increment.**

### Fields in RTP Packets That Do Increment

While SSRC does not increment, other fields in the RTP protocol do:

| Field | Increments? | Increment Rule | Purpose |
|-------|-------------|----------------|---------|
| **SSRC** | ❌ No | Randomly generated at stream start, then remains constant | Identifies stream source |
| **Sequence Number** | ✅ Yes | Increments by 1 for each packet | Detects packet loss and reordering |
| **Timestamp** | ✅ Yes | Increments by sample count | Synchronizes playback and calculates jitter |

### Code Example

Here's a key code snippet from this project's RTP streaming implementation (from `.github/workflows/create_rtp_pr.yml`):

```python
# SSRC is randomly generated once at stream start
ssrc = random.getrandbits(32)

# Sequence number and timestamp initialization
seq = random.randint(0, 0xFFFF)
timestamp = random.randint(0, 0x7FFFFFFF)

# When sending each packet
while True:  # Simplified for illustration
    # Build RTP header using the same ssrc
    header = _build_rtp_header(
        seq & 0xFFFF,           # Sequence number (increments)
        timestamp & 0xFFFFFFFF, # Timestamp (increments)
        ssrc,                    # SSRC (constant)
        payload_type,
        marker
    )
    
    # Send packet
    transport.sendto(header + payload)
    
    # Sequence number increments by 1
    seq = (seq + 1) & 0xFFFF
    
    # Timestamp increments by audio samples
    timestamp = (timestamp + samples_per_packet) & 0xFFFFFFFF
```

## RTP Header Structure

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CC   |M|     PT      |       Sequence Number         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           Timestamp                            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                     SSRC (Synchronization Source)              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

## Practical Example

### Scenario: Audio Stream Transmission

Assuming an audio stream at 8kHz sample rate, with 160 samples per packet (20ms):

| Packet # | Sequence | Timestamp | SSRC | Notes |
|----------|----------|-----------|------|-------|
| 1 | 12345 | 1000000 | **0x9A3B5C7D** | Initial values |
| 2 | 12346 (+1) | 1000160 (+160) | **0x9A3B5C7D** | SSRC unchanged |
| 3 | 12347 (+1) | 1000320 (+160) | **0x9A3B5C7D** | SSRC unchanged |
| 4 | 12348 (+1) | 1000480 (+160) | **0x9A3B5C7D** | SSRC unchanged |
| ... | ... | ... | **0x9A3B5C7D** | SSRC always constant |

## Common Misconceptions

### ❌ Incorrect Understanding
- SSRC increments with each packet
- SSRC is used for packet ordering
- SSRC changes over time

### ✅ Correct Understanding
- SSRC remains constant throughout the stream's lifetime
- Sequence number is used for ordering and detecting packet loss
- Timestamp is used for synchronization and playback
- SSRC only changes when the stream restarts or a collision occurs

## References

- [RFC 3550 - RTP: A Transport Protocol for Real-Time Applications](https://tools.ietf.org/html/rfc3550)
- [RFC 3551 - RTP Profile for Audio and Video Conferences](https://tools.ietf.org/html/rfc3551)

## Implementation in This Project

This project's RTP streaming implementation is planned to be added in the `src/utils/stream_rtp_streaming.py` file. The implementation:

- Generates SSRC using a 32-bit random number
- Maintains the same SSRC throughout the stream transmission
- Correctly increments sequence number and timestamp
- Supports RTP encapsulation for L16 audio format

## Summary

**SSRC (Synchronization Source Identifier) is a unique identifier in the RTP protocol used to identify stream sources. It remains constant throughout the entire stream transmission and does not increment. The fields that actually increment are the sequence number (increments by 1 per packet) and timestamp (increments by sample count).**
