#!/usr/bin/env python3
"""
Local UDP Sink - Test tool for receiving RTP audio data.

This script creates a UDP socket that listens for incoming RTP packets
and saves the received audio payload to a raw PCM file.

Usage:
    python local_udp_sink.py [--port PORT] [--output FILE] [--timeout SECONDS]

Example:
    # Start the UDP sink on port 5000, save to output.pcm
    python local_udp_sink.py --port 5000 --output output.pcm
    
    # Then send TTS data to localhost:5000 using the API:
    curl -X POST "http://localhost:8210/stream-rtp-streaming/" \\
         -H "Content-Type: application/json" \\
         -d '{"text":"你好，Hello World!", "voice":"zf_001", "target_host":"127.0.0.1", "target_port":5000}'

Converting raw PCM to WAV:
    # For PCMU (G.711 μ-law) at 8kHz:
    ffmpeg -f mulaw -ar 8000 -ac 1 -i output.pcm output.wav
    
    # For L16 (Linear 16-bit PCM) at 8kHz:
    ffmpeg -f s16le -ar 8000 -ac 1 -i output.pcm output.wav
"""

import argparse
import socket
import struct
import sys
import time
import signal
from datetime import datetime


def parse_rtp_header(data: bytes) -> dict:
    """
    Parse RTP header from packet data.
    
    RTP Header format (12 bytes minimum):
    - Byte 0: V(2 bits) | P(1) | X(1) | CC(4)
    - Byte 1: M(1 bit) | PT(7 bits)
    - Bytes 2-3: Sequence number (16 bits)
    - Bytes 4-7: Timestamp (32 bits)
    - Bytes 8-11: SSRC (32 bits)
    """
    if len(data) < 12:
        return None
    
    byte0 = data[0]
    byte1 = data[1]
    
    version = (byte0 >> 6) & 0x03
    padding = (byte0 >> 5) & 0x01
    extension = (byte0 >> 4) & 0x01
    cc = byte0 & 0x0F
    
    marker = (byte1 >> 7) & 0x01
    payload_type = byte1 & 0x7F
    
    seq_num = struct.unpack('!H', data[2:4])[0]
    timestamp = struct.unpack('!I', data[4:8])[0]
    ssrc = struct.unpack('!I', data[8:12])[0]
    
    header_len = 12 + (cc * 4)  # CSRC list
    
    return {
        'version': version,
        'padding': padding,
        'extension': extension,
        'cc': cc,
        'marker': marker,
        'payload_type': payload_type,
        'seq_num': seq_num,
        'timestamp': timestamp,
        'ssrc': ssrc,
        'header_len': header_len
    }


def run_udp_sink(port: int, output_file: str, timeout: float = 60.0, verbose: bool = True, bind_addr: str = '127.0.0.1'):
    """
    Run the UDP sink to receive RTP packets.
    
    Args:
        port: UDP port to listen on
        output_file: Path to save raw PCM data
        timeout: Inactivity timeout in seconds (0 = infinite)
        verbose: Print packet information
        bind_addr: IP address to bind to (default: 127.0.0.1 for security)
    
    Security Note:
        By default, binds to 127.0.0.1 (localhost only). Use --bind 0.0.0.0
        only when you need to receive packets from other machines and understand
        the security implications.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, port))
    
    if timeout > 0:
        sock.settimeout(timeout)
    
    print(f"UDP Sink listening on {bind_addr}:{port}")
    print(f"Output file: {output_file}")
    print(f"Timeout: {timeout}s (0 = infinite)")
    print("Press Ctrl+C to stop\n")
    
    running = True
    packet_count = 0
    total_bytes = 0
    first_packet_time = None
    last_seq = None
    
    def signal_handler(signum, frame):
        nonlocal running
        print("\nReceived shutdown signal")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        with open(output_file, 'wb') as f:
            while running:
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    print(f"\nTimeout after {timeout}s of inactivity")
                    break
                except OSError:
                    break
                
                if not data:
                    continue
                
                rtp = parse_rtp_header(data)
                if rtp is None:
                    if verbose:
                        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Non-RTP packet ({len(data)} bytes) from {addr}")
                    continue
                
                # Extract payload (after RTP header)
                payload = data[rtp['header_len']:]
                
                if packet_count == 0:
                    first_packet_time = time.time()
                    print(f"First packet received from {addr}")
                    print(f"  SSRC: {rtp['ssrc']:08X}")
                    print(f"  Payload Type: {rtp['payload_type']}")
                    print()
                
                # Check for sequence number gaps
                if last_seq is not None:
                    expected_seq = (last_seq + 1) & 0xFFFF
                    if rtp['seq_num'] != expected_seq:
                        gap = (rtp['seq_num'] - last_seq) & 0xFFFF
                        if gap > 1:
                            print(f"  [!] Sequence gap: {gap - 1} packets lost (expected {expected_seq}, got {rtp['seq_num']})")
                
                last_seq = rtp['seq_num']
                
                # Write payload to file
                f.write(payload)
                total_bytes += len(payload)
                packet_count += 1
                
                if verbose and packet_count % 100 == 0:
                    elapsed = time.time() - first_packet_time if first_packet_time else 0
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Packets: {packet_count}, "
                          f"Bytes: {total_bytes}, Elapsed: {elapsed:.1f}s")
                
                # Check for marker bit (end of stream)
                if rtp['marker']:
                    print(f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                          f"Marker packet received (end of stream)")
    
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        sock.close()
        
        # Print summary
        elapsed = time.time() - first_packet_time if first_packet_time else 0
        print(f"\n{'='*50}")
        print(f"Summary:")
        print(f"  Total packets: {packet_count}")
        print(f"  Total payload bytes: {total_bytes}")
        print(f"  Duration: {elapsed:.2f}s")
        if elapsed > 0:
            print(f"  Average bitrate: {(total_bytes * 8) / elapsed / 1000:.1f} kbps")
        print(f"  Output saved to: {output_file}")
        print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(
        description='UDP Sink for receiving RTP audio packets',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=5000,
        help='UDP port to listen on (default: 5000)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='received_audio.pcm',
        help='Output file for raw PCM data (default: received_audio.pcm)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=float,
        default=60.0,
        help='Inactivity timeout in seconds (0 = infinite, default: 60)'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress per-packet output'
    )
    parser.add_argument(
        '--bind', '-b',
        type=str,
        default='127.0.0.1',
        help='IP address to bind to (default: 127.0.0.1, use 0.0.0.0 for all interfaces)'
    )
    
    args = parser.parse_args()
    
    run_udp_sink(
        port=args.port,
        output_file=args.output,
        timeout=args.timeout,
        verbose=not args.quiet,
        bind_addr=args.bind
    )


if __name__ == '__main__':
    main()
