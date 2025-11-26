#!/usr/bin/env python3
"""
本地 UDP 音频接收器测试脚本。

用于测试 /synthesize/ 接口的 socket 发送功能。
启动后监听指定端口，将接收到的音频数据写入文件。

使用方法:
    python scripts/local_udp_sink.py --port 5200 --output received_audio.pcm
    
然后调用 API:
    curl -X POST "http://localhost:8210/synthesize/" \
         -H "Content-Type: application/json" \
         -d '{"text":"你好，hello world", "voice":"zf_001", "ip":"127.0.0.1", "port":5200}'

播放录制的音频 (需要安装 ffplay 或 sox):
    ffplay -f s16le -ar 24000 -ac 1 received_audio.pcm
    # 或
    sox -r 24000 -c 1 -b 16 -e signed-integer received_audio.pcm received_audio.wav
"""

import socket
import argparse
import logging
import time
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [UDP-Sink] %(levelname)s: %(message)s"
)
logger = logging.getLogger("udp_sink")


def run_udp_receiver(host: str, port: int, output_path: str, timeout: float = 30.0):
    """
    运行 UDP 接收器，将收到的数据写入文件。
    
    Args:
        host: 监听地址
        port: 监听端口
        output_path: 输出文件路径
        timeout: 无数据超时时间（秒）
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.settimeout(1.0)  # 1 second timeout for periodic checks
    
    logger.info(f"Listening on {host}:{port}, output to: {output_path}")
    logger.info(f"Will timeout after {timeout}s of no data")
    
    total_bytes = 0
    packet_count = 0
    last_data_time = time.time()
    start_time = None
    
    with open(output_path, 'wb') as f:
        try:
            while True:
                try:
                    data, addr = sock.recvfrom(65536)
                    
                    if start_time is None:
                        start_time = time.time()
                        logger.info(f"First packet received from {addr}")
                    
                    # Write data to file
                    f.write(data)
                    f.flush()
                    
                    total_bytes += len(data)
                    packet_count += 1
                    last_data_time = time.time()
                    
                    # Log progress periodically
                    if packet_count % 100 == 0:
                        elapsed = time.time() - start_time
                        logger.info(f"Received {packet_count} packets, {total_bytes} bytes in {elapsed:.1f}s")
                    
                except socket.timeout:
                    # Check for overall timeout
                    if time.time() - last_data_time > timeout:
                        logger.info(f"Timeout reached ({timeout}s with no data)")
                        break
                    continue
                    
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            sock.close()
    
    # Summary
    if start_time:
        total_time = time.time() - start_time
        logger.info(f"=== Summary ===")
        logger.info(f"Total packets: {packet_count}")
        logger.info(f"Total bytes: {total_bytes}")
        logger.info(f"Duration: {total_time:.2f}s")
        logger.info(f"Output file: {output_path}")
        
        # Estimate audio duration (assuming 16-bit, 24kHz, mono)
        audio_duration = total_bytes / (24000 * 2)  # 2 bytes per sample
        logger.info(f"Estimated audio duration: {audio_duration:.2f}s")
    else:
        logger.warning("No data received")


def run_tcp_receiver(host: str, port: int, output_path: str, timeout: float = 30.0):
    """
    运行 TCP 接收器，将收到的数据写入文件。
    
    Args:
        host: 监听地址
        port: 监听端口
        output_path: 输出文件路径
        timeout: 无数据超时时间（秒）
    """
    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Create TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(1)
    sock.settimeout(timeout)
    
    logger.info(f"TCP server listening on {host}:{port}, output to: {output_path}")
    logger.info(f"Waiting for connection (timeout: {timeout}s)")
    
    try:
        conn, addr = sock.accept()
        logger.info(f"Connection from {addr}")
        conn.settimeout(1.0)
        
        total_bytes = 0
        start_time = time.time()
        last_data_time = time.time()
        
        with open(output_path, 'wb') as f:
            try:
                while True:
                    try:
                        data = conn.recv(65536)
                        if not data:
                            logger.info("Connection closed by peer")
                            break
                        
                        f.write(data)
                        f.flush()
                        
                        total_bytes += len(data)
                        last_data_time = time.time()
                        
                    except socket.timeout:
                        if time.time() - last_data_time > timeout:
                            logger.info(f"Timeout reached")
                            break
                        continue
                        
            finally:
                conn.close()
        
        # Summary
        total_time = time.time() - start_time
        logger.info(f"=== Summary ===")
        logger.info(f"Total bytes: {total_bytes}")
        logger.info(f"Duration: {total_time:.2f}s")
        logger.info(f"Output file: {output_path}")
        
    except socket.timeout:
        logger.warning("No connection received within timeout")
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser(
        description="Local audio receiver for testing synthesize API socket output"
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5200, help="Bind port (default: 5200)")
    parser.add_argument("--output", "-o", default="received_audio.pcm", help="Output file path")
    parser.add_argument("--protocol", choices=["udp", "tcp"], default="udp", help="Protocol (default: udp)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Timeout in seconds (default: 30)")
    
    args = parser.parse_args()
    
    if args.protocol == "udp":
        run_udp_receiver(args.host, args.port, args.output, args.timeout)
    else:
        run_tcp_receiver(args.host, args.port, args.output, args.timeout)


if __name__ == "__main__":
    main()
