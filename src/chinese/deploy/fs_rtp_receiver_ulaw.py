#!/usr/bin/env python3
"""
RTP 接收器：接收 RTP 包 (header + payload)。
如果 payload 为 PCMU（payload_type=0），则解码为 16-bit PCM（little-endian）再写入 FIFO（/tmp/remote_stream.pcm）。
如果 payload 为 L16（payload_type dynamic），则直接把 payload 写入（假设为 16-bit LE）。
该脚本简单实现：剥离 RTP 12 字节 header，读取 payload_type 并据此处理。
"""
import socket
import argparse
import logging
import os
import time
import struct
import audioop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [rtp_receiver] %(levelname)s: %(message)s")
logger = logging.getLogger("rtp_receiver")

def ensure_fifo(path):
    if not os.path.exists(path):
        try:
            os.mkfifo(path, 0o666)
            logger.info(f"Created FIFO at {path}")
        except Exception:
            logger.warning("Failed to create FIFO (may treat as normal file)")

def open_fifo_nonblocking(path):
    import errno
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        return os.fdopen(fd, "ab", buffering=0)
    except OSError as e:
        if e.errno in (errno.ENXIO, errno.ENOENT):
            return None
        raise

def run_server(host: str, port: int, out_path: str):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    ensure_fifo(out_path)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(1.0)
    logger.info(f"Listening RTP (UDP) on {host}:{port}, writing to {out_path}")

    writer = None
    last_try = 0
    try:
        while True:
            try:
                packet, addr = sock.recvfrom(65536)
            except socket.timeout:
                # periodically try open writer
                if writer is None and (time.time() - last_try) > 1.0:
                    last_try = time.time()
                    writer = open_fifo_nonblocking(out_path)
                continue
            if not packet or len(packet) <= 12:
                continue
            # parse RTP header first two bytes to get payload type
            b0 = packet[0]
            b1 = packet[1]
            payload_type = b1 & 0x7F
            # payload = packet[12:]  # ignoring CSRC/extension — assume simple packets
            # handle payload
            payload = packet[12:]

            if payload_type == 0:  # PCMU (G.711 μ-law)
                # decode μ-law -> 16-bit linear (width=2)
                try:
                    pcm16 = audioop.ulaw2lin(payload, 2)
                except Exception:
                    logger.exception("ulaw2lin failed")
                    continue
                to_write = pcm16
            else:
                # assume L16 16-bit little-endian
                to_write = payload

            if writer is None:
                writer = open_fifo_nonblocking(out_path)
                if writer is None:
                    # no reader yet, drop packet (or buffer if you prefer)
                    logger.debug("No FIFO reader, dropping packet")
                    continue

            try:
                writer.write(to_write)
                writer.flush()
            except BrokenPipeError:
                logger.warning("Reader closed, dropping until reader reappears")
                try:
                    writer.close()
                except Exception:
                    pass
                writer = None
                continue
    except KeyboardInterrupt:
        logger.info("Receiver stopped by user")
    finally:
        if writer:
            try:
                writer.close()
            except Exception:
                pass
        sock.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--out", default="/tmp/remote_stream.pcm")
    args = p.parse_args()
    run_server(args.host, args.port, args.out)