#!/usr/bin/env python3
"""
local_udp_sink.py - Local UDP Listener for E2E Testing

Listens on a specified UDP port and writes received RTP audio data to a raw PCM file.
Useful for manually verifying that the stream_rtp_streaming_endpoint works correctly
with mixed Chinese/English text.

Usage:
    python local_udp_sink.py --port 5004 --output received_audio.raw

Then send audio using the API:
    curl -X POST "http://localhost:8210/stream-rtp-streaming/" \
         -H "Content-Type: application/json" \
         -d '{"text":"你好Hello世界", "voice":"zf_001", "target_host":"127.0.0.1", "target_port":5004}'

The received raw PCM can be played with:
    ffplay -f mulaw -ar 8000 -ac 1 received_audio.raw
    # or for L16:
    ffplay -f s16le -ar 8000 -ac 1 received_audio.raw
"""

import argparse
import socket
import struct
import sys
import signal
from datetime import datetime


def parse_rtp_header(data: bytes) -> dict:
    """
    Parse RTP header from packet data.
    
    Returns dict with:
        - version: RTP version
        - padding: Padding flag
        - extension: Extension flag
        - csrc_count: CSRC count
        - marker: Marker bit
        - payload_type: Payload type
        - sequence: Sequence number
        - timestamp: Timestamp
        - ssrc: SSRC
        - payload: Payload data
    """
    if len(data) < 12:
        return None
    
    byte0, byte1 = data[0], data[1]
    version = (byte0 >> 6) & 0x03
    padding = (byte0 >> 5) & 0x01
    extension = (byte0 >> 4) & 0x01
    csrc_count = byte0 & 0x0F
    marker = (byte1 >> 7) & 0x01
    payload_type = byte1 & 0x7F
    
    sequence = struct.unpack('>H', data[2:4])[0]
    timestamp = struct.unpack('>I', data[4:8])[0]
    ssrc = struct.unpack('>I', data[8:12])[0]
    
    header_size = 12 + (csrc_count * 4)
    if extension:
        if len(data) < header_size + 4:
            return None
        ext_length = struct.unpack('>H', data[header_size+2:header_size+4])[0]
        header_size += 4 + (ext_length * 4)
    
    payload = data[header_size:] if len(data) > header_size else b''
    
    return {
        'version': version,
        'padding': padding,
        'extension': extension,
        'csrc_count': csrc_count,
        'marker': marker,
        'payload_type': payload_type,
        'sequence': sequence,
        'timestamp': timestamp,
        'ssrc': ssrc,
        'payload': payload
    }


def main():
    parser = argparse.ArgumentParser(
        description='UDP sink for receiving RTP audio streams'
    )
    parser.add_argument(
        '--port', '-p', 
        type=int, 
        default=5004,
        help='UDP port to listen on (default: 5004)'
    )
    parser.add_argument(
        '--host', 
        type=str, 
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='received_audio.raw',
        help='Output file for raw PCM data (default: received_audio.raw)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=float,
        default=30.0,
        help='Timeout in seconds to wait for packets (default: 30)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output showing RTP packet info'
    )
    
    args = parser.parse_args()
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(args.timeout)
    
    try:
        sock.bind((args.host, args.port))
        print(f"[{datetime.now().isoformat()}] Listening on {args.host}:{args.port}")
        print(f"Output file: {args.output}")
        print("Press Ctrl+C to stop...")
    except Exception as e:
        print(f"Failed to bind to {args.host}:{args.port}: {e}")
        sys.exit(1)
    
    # Setup signal handler for graceful shutdown
    running = True
    def signal_handler(sig, frame):
        nonlocal running
        print("\nShutting down...")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    packet_count = 0
    total_bytes = 0
    last_ssrc = None
    
    with open(args.output, 'wb') as f:
        while running:
            try:
                data, addr = sock.recvfrom(4096)
                
                rtp = parse_rtp_header(data)
                if rtp is None:
                    if args.verbose:
                        print(f"[{datetime.now().isoformat()}] Received non-RTP packet from {addr}, len={len(data)}")
                    continue
                
                # Detect SSRC change (new stream)
                if last_ssrc is not None and rtp['ssrc'] != last_ssrc:
                    print(f"[{datetime.now().isoformat()}] SSRC changed: {last_ssrc} -> {rtp['ssrc']}")
                last_ssrc = rtp['ssrc']
                
                # Write payload to file
                f.write(rtp['payload'])
                f.flush()
                
                packet_count += 1
                total_bytes += len(rtp['payload'])
                
                if args.verbose:
                    print(f"[{datetime.now().isoformat()}] Packet #{packet_count} from {addr}: "
                          f"seq={rtp['sequence']}, ts={rtp['timestamp']}, "
                          f"pt={rtp['payload_type']}, marker={rtp['marker']}, "
                          f"payload_len={len(rtp['payload'])}")
                elif packet_count % 50 == 0:
                    print(f"[{datetime.now().isoformat()}] Received {packet_count} packets, {total_bytes} bytes")
                
                # Check for marker bit (end of stream)
                if rtp['marker']:
                    print(f"[{datetime.now().isoformat()}] End of stream marker received")
                    
            except socket.timeout:
                if packet_count > 0:
                    print(f"[{datetime.now().isoformat()}] Timeout - no packets for {args.timeout}s")
                    break
                # Continue waiting if no packets received yet
                continue
            except Exception as e:
                if running:
                    print(f"Error receiving data: {e}")
                break
    
    sock.close()
    print(f"\n[{datetime.now().isoformat()}] Finished. "
          f"Received {packet_count} packets, {total_bytes} bytes total.")
    print(f"Raw audio saved to: {args.output}")
    print("\nTo play the audio:")
    print(f"  For PCMU: ffplay -f mulaw -ar 8000 -ac 1 {args.output}")
    print(f"  For L16:  ffplay -f s16le -ar 8000 -ac 1 {args.output}")


if __name__ == '__main__':
    main()
