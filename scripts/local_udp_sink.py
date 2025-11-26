#!/usr/bin/env python3
"""
Local UDP sink for testing RTP streaming.

This script listens on a specified UDP port and receives RTP packets,
optionally decoding PCMU/L16 payloads and saving to a PCM file for verification.

Usage:
    python local_udp_sink.py --port 9000 --output /tmp/received_audio.pcm

The received audio can be played using:
    - For PCMU (8kHz): aplay -f MU_LAW -r 8000 -c 1 /tmp/received_audio.pcm
    - For L16 (8kHz): aplay -f S16_LE -r 8000 -c 1 /tmp/received_audio.pcm
"""

import socket
import argparse
import logging
import audioop
import sys
import signal
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [udp_sink] %(levelname)s: %(message)s"
)
logger = logging.getLogger("udp_sink")


class UDPSink:
    """UDP listener that receives and processes RTP packets."""
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        output_path: Optional[str] = None,
        decode_pcmu: bool = True,
        max_packets: Optional[int] = None,
    ):
        """
        Initialize UDP sink.
        
        Args:
            host: Host to bind to (default: 0.0.0.0).
            port: Port to listen on (default: 9000).
            output_path: Optional path to save received audio.
            decode_pcmu: Whether to decode PCMU to linear PCM (default: True).
            max_packets: Maximum number of packets to receive before stopping.
        """
        self.host = host
        self.port = port
        self.output_path = output_path
        self.decode_pcmu = decode_pcmu
        self.max_packets = max_packets
        self.running = False
        self.packet_count = 0
        self.bytes_received = 0
        self.sock: Optional[socket.socket] = None
        self.output_file = None
    
    def parse_rtp_header(self, packet: bytes) -> dict:
        """
        Parse RTP header from packet.
        
        Args:
            packet: Raw RTP packet bytes.
            
        Returns:
            Dictionary with header fields.
        """
        if len(packet) < 12:
            return {}
        
        b0 = packet[0]
        b1 = packet[1]
        
        version = (b0 >> 6) & 0x03
        padding = (b0 >> 5) & 0x01
        extension = (b0 >> 4) & 0x01
        cc = b0 & 0x0F
        
        marker = (b1 >> 7) & 0x01
        payload_type = b1 & 0x7F
        
        seq = (packet[2] << 8) | packet[3]
        timestamp = (packet[4] << 24) | (packet[5] << 16) | (packet[6] << 8) | packet[7]
        ssrc = (packet[8] << 24) | (packet[9] << 16) | (packet[10] << 8) | packet[11]
        
        return {
            "version": version,
            "padding": padding,
            "extension": extension,
            "cc": cc,
            "marker": marker,
            "payload_type": payload_type,
            "seq": seq,
            "timestamp": timestamp,
            "ssrc": ssrc,
        }
    
    def decode_payload(self, payload: bytes, payload_type: int) -> bytes:
        """
        Decode RTP payload based on payload type.
        
        Args:
            payload: Raw payload bytes.
            payload_type: RTP payload type.
            
        Returns:
            Decoded audio bytes (linear PCM).
        """
        if payload_type == 0 and self.decode_pcmu:
            # PCMU (G.711 μ-law) -> 16-bit linear PCM
            try:
                return audioop.ulaw2lin(payload, 2)
            except Exception as e:
                logger.warning(f"Failed to decode PCMU: {e}")
                return payload
        else:
            # L16 or other - return as-is
            return payload
    
    def start(self):
        """Start listening for UDP packets."""
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.host, self.port))
        self.sock.settimeout(1.0)
        
        if self.output_path:
            self.output_file = open(self.output_path, "wb")
        
        logger.info(f"Listening on {self.host}:{self.port}")
        if self.output_path:
            logger.info(f"Saving audio to {self.output_path}")
        
        try:
            while self.running:
                try:
                    packet, addr = self.sock.recvfrom(65536)
                except socket.timeout:
                    continue
                
                if not packet or len(packet) <= 12:
                    continue
                
                self.packet_count += 1
                self.bytes_received += len(packet)
                
                # Parse header
                header = self.parse_rtp_header(packet)
                payload = packet[12:]
                
                # Log packet info periodically
                if self.packet_count == 1 or self.packet_count % 100 == 0:
                    logger.info(
                        f"Packet #{self.packet_count}: "
                        f"from={addr}, "
                        f"pt={header.get('payload_type')}, "
                        f"seq={header.get('seq')}, "
                        f"ssrc={header.get('ssrc'):08x}, "
                        f"payload_len={len(payload)}"
                    )
                
                # Decode and save
                if self.output_file:
                    decoded = self.decode_payload(payload, header.get("payload_type", 96))
                    self.output_file.write(decoded)
                
                # Check packet limit
                if self.max_packets and self.packet_count >= self.max_packets:
                    logger.info(f"Reached max packets ({self.max_packets}), stopping")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Stopped by user")
        finally:
            self.stop()
    
    def stop(self):
        """Stop listening and cleanup."""
        self.running = False
        
        if self.output_file:
            self.output_file.close()
            self.output_file = None
        
        if self.sock:
            self.sock.close()
            self.sock = None
        
        logger.info(
            f"Stopped. Received {self.packet_count} packets, "
            f"{self.bytes_received} bytes total"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Local UDP sink for testing RTP streaming"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9000,
        help="Port to listen on (default: 9000)"
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Path to save received audio (PCM format)"
    )
    parser.add_argument(
        "--no-decode",
        action="store_true",
        help="Don't decode PCMU, save raw payload"
    )
    parser.add_argument(
        "--max-packets",
        type=int,
        default=None,
        help="Maximum number of packets to receive"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    sink = UDPSink(
        host=args.host,
        port=args.port,
        output_path=args.output,
        decode_pcmu=not args.no_decode,
        max_packets=args.max_packets,
    )
    
    # Handle signals gracefully
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, stopping...")
        sink.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    sink.start()


if __name__ == "__main__":
    main()
