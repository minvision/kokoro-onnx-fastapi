"""
Stream sender module for sending audio data to specified IP:port.
Supports UDP and TCP protocols.
"""

import asyncio
import socket
import logging
from typing import Optional, AsyncIterator, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class Protocol(str, Enum):
    """Supported network protocols."""
    UDP = "udp"
    TCP = "tcp"


class StreamSender:
    """
    Asynchronous audio stream sender.
    Sends audio chunks to specified IP:port via UDP or TCP.
    """
    
    def __init__(
        self,
        host: str,
        port: int,
        protocol: Protocol = Protocol.UDP,
        buffer_size: int = 4096
    ):
        """
        Initialize stream sender.
        
        Args:
            host: Target IP address
            port: Target port number
            protocol: Network protocol (UDP or TCP)
            buffer_size: Send buffer size in bytes
        """
        self.host = host
        self.port = port
        self.protocol = Protocol(protocol.lower()) if isinstance(protocol, str) else protocol
        self.buffer_size = buffer_size
        self._transport = None
        self._writer = None
        self._connected = False
        self._error_count = 0
        self._max_errors = 10
        
    async def connect(self) -> bool:
        """
        Establish connection to target.
        For UDP, this creates a datagram endpoint.
        For TCP, this opens a stream connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            loop = asyncio.get_running_loop()
            
            if self.protocol == Protocol.UDP:
                # Create UDP datagram endpoint
                self._transport, _ = await loop.create_datagram_endpoint(
                    lambda: asyncio.DatagramProtocol(),
                    remote_addr=(self.host, self.port)
                )
                self._connected = True
                logger.info(f"[StreamSender] UDP endpoint created for {self.host}:{self.port}")
                
            elif self.protocol == Protocol.TCP:
                # Create TCP connection
                _, self._writer = await asyncio.open_connection(self.host, self.port)
                self._connected = True
                logger.info(f"[StreamSender] TCP connection established to {self.host}:{self.port}")
            
            return True
            
        except Exception as e:
            logger.warning(f"[StreamSender] Failed to connect to {self.host}:{self.port}: {e}")
            self._connected = False
            return False
    
    async def send(self, data: bytes) -> bool:
        """
        Send data chunk to target.
        
        Args:
            data: Bytes to send
            
        Returns:
            True if send successful, False otherwise
        """
        if not data:
            return True
            
        if not self._connected:
            # Try to auto-connect
            if not await self.connect():
                return False
        
        try:
            if self.protocol == Protocol.UDP:
                if self._transport:
                    self._transport.sendto(data)
                    self._error_count = 0
                    return True
                    
            elif self.protocol == Protocol.TCP:
                if self._writer:
                    self._writer.write(data)
                    await self._writer.drain()
                    self._error_count = 0
                    return True
            
            return False
            
        except Exception as e:
            self._error_count += 1
            if self._error_count <= 3:  # Only log first few errors
                logger.warning(f"[StreamSender] Send failed to {self.host}:{self.port}: {e}")
            
            if self._error_count >= self._max_errors:
                logger.error(f"[StreamSender] Too many errors ({self._error_count}), marking as disconnected")
                self._connected = False
            
            return False
    
    async def send_chunked(
        self, 
        data: bytes, 
        chunk_size: Optional[int] = None
    ) -> int:
        """
        Send data in chunks.
        
        Args:
            data: Full data bytes
            chunk_size: Size of each chunk (default: buffer_size)
            
        Returns:
            Number of bytes successfully sent
        """
        chunk_size = chunk_size or self.buffer_size
        sent_bytes = 0
        
        for i in range(0, len(data), chunk_size):
            chunk = data[i:i + chunk_size]
            if await self.send(chunk):
                sent_bytes += len(chunk)
        
        return sent_bytes
    
    async def close(self):
        """Close the connection."""
        try:
            if self.protocol == Protocol.UDP:
                if self._transport:
                    self._transport.close()
                    self._transport = None
                    
            elif self.protocol == Protocol.TCP:
                if self._writer:
                    self._writer.close()
                    await self._writer.wait_closed()
                    self._writer = None
            
            self._connected = False
            logger.debug(f"[StreamSender] Connection closed for {self.host}:{self.port}")
            
        except Exception as e:
            logger.warning(f"[StreamSender] Error closing connection: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._connected
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


async def create_stream_sender(
    host: str,
    port: int,
    protocol: str = "udp"
) -> Optional[StreamSender]:
    """
    Factory function to create and connect a StreamSender.
    
    Args:
        host: Target IP address
        port: Target port number
        protocol: "udp" or "tcp"
        
    Returns:
        Connected StreamSender or None if connection failed
    """
    sender = StreamSender(host, port, protocol)
    if await sender.connect():
        return sender
    return None


async def stream_with_sender(
    audio_generator: AsyncIterator[bytes],
    host: str,
    port: int,
    protocol: str = "udp",
    on_chunk: Optional[Callable[[bytes], None]] = None
) -> AsyncIterator[bytes]:
    """
    Wrap an audio generator to also send chunks to IP:port.
    
    This generator yields the same chunks as the input generator
    while simultaneously sending them to the specified target.
    
    Args:
        audio_generator: Async iterator yielding audio bytes
        host: Target IP address
        port: Target port number
        protocol: "udp" or "tcp"
        on_chunk: Optional callback for each chunk
        
    Yields:
        Audio byte chunks (same as input generator)
    """
    sender = StreamSender(host, port, protocol)
    connected = await sender.connect()
    
    if not connected:
        logger.warning(f"[stream_with_sender] Could not connect to {host}:{port}, "
                      f"continuing without socket streaming")
    
    try:
        async for chunk in audio_generator:
            # Send to socket (ignore errors to not break HTTP response)
            if connected:
                await sender.send(chunk)
            
            # Optional callback
            if on_chunk:
                on_chunk(chunk)
            
            # Yield to HTTP response
            yield chunk
            
    finally:
        await sender.close()


class DualOutputStreamer:
    """
    Streams audio data to both HTTP response and socket simultaneously.
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        protocol: str = "udp"
    ):
        """
        Initialize dual output streamer.
        
        Args:
            host: Target IP (None to disable socket streaming)
            port: Target port (None to disable socket streaming)
            protocol: "udp" or "tcp"
        """
        self.host = host
        self.port = port
        self.protocol = protocol
        self._sender: Optional[StreamSender] = None
        self._enable_socket = host is not None and port is not None
        
    async def start(self) -> bool:
        """Start the streamer and connect to socket if enabled."""
        if self._enable_socket:
            self._sender = StreamSender(self.host, self.port, self.protocol)
            return await self._sender.connect()
        return True
    
    async def send_chunk(self, chunk: bytes) -> bytes:
        """
        Send chunk to socket and return it for HTTP response.
        
        Args:
            chunk: Audio bytes
            
        Returns:
            Same chunk (for yielding to HTTP response)
        """
        if self._sender and self._sender.is_connected:
            await self._sender.send(chunk)
        return chunk
    
    async def stop(self):
        """Stop the streamer and close socket connection."""
        if self._sender:
            await self._sender.close()
            self._sender = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
