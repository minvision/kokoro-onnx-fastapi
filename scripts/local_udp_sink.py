#!/usr/bin/env python3
"""
Local UDP Sink - Listens on a UDP port and writes received data to a file.

This script is used for testing the RTP/UDP streaming functionality of the
Chinese TTS service. It captures UDP packets and saves them to a file for
analysis or playback.

Usage:
    python local_udp_sink.py [--port PORT] [--output OUTPUT_FILE]

Examples:
    # Listen on default port 5004 and save to output.raw
    python local_udp_sink.py
    
    # Listen on port 9999 and save to my_audio.raw
    python local_udp_sink.py --port 9999 --output my_audio.raw
    
    # Then send TTS to this sink using curl:
    curl -X POST "http://localhost:8210/stream-rtp-streaming/" \\
         -H "Content-Type: application/json" \\
         -d '{"text":"Hello World 你好世界", "voice":"zf_001", "target_host":"127.0.0.1", "target_port":5004}'
"""

import argparse
import socket
import sys
import signal
import os
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(
        description="UDP sink for testing RTP/TTS streaming"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=5004,
        help="UDP port to listen on (default: 5004)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="output.raw",
        help="Output file path (default: output.raw)"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=30.0,
        help="Idle timeout in seconds (default: 30.0, 0 for no timeout)"
    )
    parser.add_argument(
        "--strip-rtp-header",
        action="store_true",
        help="Strip 12-byte RTP header from packets before writing"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output including packet info"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Setup signal handler for graceful shutdown
    running = [True]
    
    def signal_handler(sig, frame):
        print("\nShutting down...")
        running[0] = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        sock.bind(("0.0.0.0", args.port))
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Listening on UDP port {args.port}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Output file: {args.output}")
        
        if args.timeout > 0:
            sock.settimeout(args.timeout)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Idle timeout: {args.timeout}s")
        
        # Open output file
        total_bytes = 0
        packet_count = 0
        
        with open(args.output, "wb") as outfile:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Waiting for packets...")
            
            while running[0]:
                try:
                    data, addr = sock.recvfrom(4096)
                    packet_count += 1
                    
                    if args.strip_rtp_header and len(data) > 12:
                        # RTP header is 12 bytes minimum
                        payload = data[12:]
                    else:
                        payload = data
                    
                    outfile.write(payload)
                    total_bytes += len(payload)
                    
                    if args.verbose:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Packet {packet_count} from {addr[0]}:{addr[1]}, "
                              f"size={len(data)} bytes, payload={len(payload)} bytes")
                    elif packet_count % 100 == 0:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Received {packet_count} packets, {total_bytes} bytes total")
                        
                except socket.timeout:
                    if packet_count > 0:
                        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Idle timeout reached after receiving data")
                        break
                    else:
                        # Reset timeout and keep waiting
                        continue
                        
                except Exception as e:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Error receiving: {e}")
                    break
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Summary:")
        print(f"  Total packets: {packet_count}")
        print(f"  Total bytes written: {total_bytes}")
        print(f"  Output file: {os.path.abspath(args.output)}")
        
        if args.strip_rtp_header:
            print("\n  Note: RTP headers were stripped. The output is raw audio payload.")
            print("  For PCMU (G.711 μ-law) at 8kHz: play with `sox -t raw -r 8000 -c 1 -e mu-law output.raw output.wav`")
            print("  For L16 at 8kHz: play with `sox -t raw -r 8000 -c 1 -e signed -b 16 output.raw output.wav`")
        else:
            print("\n  Note: Output includes RTP headers. Use --strip-rtp-header to get raw audio.")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
