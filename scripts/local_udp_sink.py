#!/usr/bin/env python3
"""
Local UDP sink for E2E testing of RTP/UDP audio streaming.

This script listens on a specified UDP port and saves received raw PCM/RTP
audio data to a file for manual verification.

Usage:
    python scripts/local_udp_sink.py [--port PORT] [--output OUTPUT_FILE] [--timeout TIMEOUT]

Examples:
    # Listen on port 5000 and save to output.raw
    python scripts/local_udp_sink.py --port 5000 --output /tmp/output.raw
    
    # Listen with 30 second timeout
    python scripts/local_udp_sink.py --port 5000 --output /tmp/output.raw --timeout 30
    
    # Convert raw PCM to WAV (8kHz, mono, 16-bit LE):
    ffmpeg -f s16le -ar 8000 -ac 1 -i /tmp/output.raw /tmp/output.wav
    
    # For PCMU/G.711:
    ffmpeg -f mulaw -ar 8000 -ac 1 -i /tmp/output.raw /tmp/output.wav
"""

import argparse
import asyncio
import logging
import os
import signal
import struct
import sys
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UDPSinkProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler that writes received data to a file."""
    
    def __init__(
        self, 
        output_file: str, 
        strip_rtp_header: bool = True,
        verbose: bool = True
    ):
        self.output_file = output_file
        self.strip_rtp_header = strip_rtp_header
        self.verbose = verbose
        self.packet_count = 0
        self.total_bytes = 0
        self.file_handle = None
        self.transport = None
        
    def connection_made(self, transport):
        self.transport = transport
        # Open file in binary append mode
        self.file_handle = open(self.output_file, 'wb')
        local_addr = transport.get_extra_info('sockname')
        logger.info(f"UDP Sink listening on {local_addr[0]}:{local_addr[1]}")
        logger.info(f"Writing audio data to: {self.output_file}")
        
    def datagram_received(self, data: bytes, addr):
        self.packet_count += 1
        
        # RTP header is 12 bytes minimum
        # If strip_rtp_header is True and packet looks like RTP, remove header
        payload = data
        if self.strip_rtp_header and len(data) >= 12:
            # Check if it looks like an RTP packet (version = 2)
            version = (data[0] >> 6) & 0x03
            if version == 2:
                # Parse RTP header to get CC (CSRC count)
                cc = data[0] & 0x0F
                header_len = 12 + (cc * 4)
                
                # Check for extension bit
                extension = (data[0] >> 4) & 0x01
                if extension and len(data) > header_len + 4:
                    ext_len = struct.unpack('>H', data[header_len+2:header_len+4])[0]
                    header_len += 4 + (ext_len * 4)
                
                if len(data) > header_len:
                    payload = data[header_len:]
        
        self.total_bytes += len(payload)
        
        if self.file_handle:
            self.file_handle.write(payload)
            self.file_handle.flush()
        
        if self.verbose and self.packet_count % 50 == 0:
            logger.info(f"Received {self.packet_count} packets, {self.total_bytes} bytes from {addr}")
    
    def error_received(self, exc):
        logger.error(f"UDP Error: {exc}")
        
    def connection_lost(self, exc):
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
        logger.info(f"Connection closed. Total: {self.packet_count} packets, {self.total_bytes} bytes")
        
    def close(self):
        if self.file_handle:
            self.file_handle.close()
            self.file_handle = None
        if self.transport:
            self.transport.close()


async def run_udp_sink(
    port: int, 
    output_file: str, 
    timeout: Optional[float] = None,
    strip_rtp_header: bool = True
):
    """
    Run the UDP sink server.
    
    Args:
        port: UDP port to listen on.
        output_file: Path to save received audio data.
        timeout: Optional timeout in seconds. If None, runs until interrupted.
        strip_rtp_header: Whether to strip RTP headers from packets.
    """
    loop = asyncio.get_running_loop()
    
    # Create UDP endpoint
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: UDPSinkProtocol(output_file, strip_rtp_header=strip_rtp_header),
        local_addr=('0.0.0.0', port)
    )
    
    logger.info(f"UDP Sink started. Press Ctrl+C to stop.")
    
    try:
        if timeout:
            logger.info(f"Will automatically stop after {timeout} seconds")
            await asyncio.sleep(timeout)
        else:
            # Run forever until cancelled
            while True:
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        protocol.close()
        logger.info(f"UDP Sink stopped. Audio saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Local UDP sink for receiving and saving RTP/UDP audio streams.',
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
        default='/tmp/udp_audio_output.raw',
        help='Output file path for raw audio data (default: /tmp/udp_audio_output.raw)'
    )
    parser.add_argument(
        '--timeout', '-t',
        type=float,
        default=None,
        help='Timeout in seconds (default: no timeout, runs until Ctrl+C)'
    )
    parser.add_argument(
        '--no-strip-header',
        action='store_true',
        help='Do not strip RTP headers from packets (save raw UDP payload)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        default=True,
        help='Verbose output (default: True)'
    )
    
    args = parser.parse_args()
    
    # Ensure output directory exists
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        logger.info("Received interrupt signal, shutting down...")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the async UDP sink
    try:
        asyncio.run(run_udp_sink(
            port=args.port,
            output_file=args.output,
            timeout=args.timeout,
            strip_rtp_header=not args.no_strip_header
        ))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == '__main__':
    main()
