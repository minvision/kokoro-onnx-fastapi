# RTP 发送工具（支持重用外部 transport/ssrc/seq/timestamp）
import asyncio
import random
import logging
import audioop
from typing import Optional, AsyncGenerator, Tuple, Dict, Any

import numpy as np

logger = logging.getLogger(__name__)


def _ensure_mono(samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples)
    if samples.ndim == 1:
        return samples
    return samples.mean(axis=1)


def _resample_linear(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return samples
    samples = np.asarray(samples)
    duration = samples.shape[0] / float(orig_sr)
    new_len = max(1, int(round(duration * target_sr)))
    if new_len == samples.shape[0]:
        return samples
    old_idx = np.linspace(0, samples.shape[0] - 1, samples.shape[0])
    new_idx = np.linspace(0, samples.shape[0] - 1, new_len)
    res = np.interp(new_idx, old_idx, samples).astype(samples.dtype)
    return res


def _float_to_int16_bytes(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    int16 = (clipped * 32767.0).astype(np.int16)
    # ensure little-endian
    if int16.dtype.byteorder == ">" or (int16.dtype.byteorder == "=" and np.little_endian is False):
        int16 = int16.byteswap()
    return int16.tobytes()


def _build_rtp_header(seq: int, timestamp: int, ssrc: int, payload_type: int = 96, marker: int = 0) -> bytes:
    b0 = 0x80
    b1 = (marker << 7) | (payload_type & 0x7F)
    header = bytearray(12)
    header[0] = b0
    header[1] = b1
    header[2] = (seq >> 8) & 0xFF
    header[3] = seq & 0xFF
    header[4] = (timestamp >> 24) & 0xFF
    header[5] = (timestamp >> 16) & 0xFF
    header[6] = (timestamp >> 8) & 0xFF
    header[7] = timestamp & 0xFF
    header[8] = (ssrc >> 24) & 0xFF
    header[9] = (ssrc >> 16) & 0xFF
    header[10] = (ssrc >> 8) & 0xFF
    header[11] = ssrc & 0xFF
    return bytes(header)


async def stream_rtp_from_asyncgen(
    host: str,
    port: int,
    async_gen: AsyncGenerator[Tuple[np.ndarray, int], None],
    *,
    realtime: bool = True,
    chunk_ms: int = 20,
    target_sr: int = 8000,
    codec: str = "l16",  # "l16" or "pcmu"
    payload_type: Optional[int] = None,
    logger_prefix: str = "",
    warmup_packets: int = 0,    # number of warmup silent packets
    reuse_transport: bool = False,
    transport=None,
    initial_ssrc: Optional[int] = None,
    initial_seq: Optional[int] = None,
    initial_timestamp: Optional[int] = None
) -> Dict[str, Any]:
    """
    Sends RTP packets from async_gen.
    - If reuse_transport=True and transport is provided, reuse it and use initial_ssrc/initial_seq/initial_timestamp.
    - Returns dict: {'final_seq': seq, 'final_timestamp': timestamp, 'ssrc': ssrc}
    """
    prefix = f"[stream_rtp_streaming]{logger_prefix} " if logger_prefix else "[stream_rtp_streaming] "
    loop = asyncio.get_running_loop()
    created_transport = None
    try:
        codec_norm = (codec or "l16").lower()
        if payload_type is None:
            payload_type = 0 if codec_norm == "pcmu" else 96
        else:
            payload_type = int(payload_type)

        # Decide on transport / ssrc / seq / timestamp
        if reuse_transport and transport is not None:
            tr = transport
            ssrc = int(initial_ssrc) if initial_ssrc is not None else random.getrandbits(32)
            seq = int(initial_seq) if initial_seq is not None else random.randint(0, 0xFFFF)
            timestamp = int(initial_timestamp) if initial_timestamp is not None else random.randint(0, 0x7FFFFFFF)
            # when reusing transport we must use sendto with destination
            send_func = lambda pkt: tr.sendto(pkt, (host, int(port)))
            logger.debug(f"{prefix}Reusing external transport for {host}:{port} ssrc={ssrc} seq={seq} timestamp={timestamp}")
        else:
            # create our own transport with remote_addr to simplify send
            tr, _ = await loop.create_datagram_endpoint(lambda: asyncio.DatagramProtocol(), remote_addr=(host, int(port)))
            created_transport = tr
            ssrc = int(initial_ssrc) if initial_ssrc is not None else random.getrandbits(32)
            seq = int(initial_seq) if initial_seq is not None else random.randint(0, 0xFFFF)
            timestamp = int(initial_timestamp) if initial_timestamp is not None else random.randint(0, 0x7FFFFFFF)
            send_func = lambda pkt: tr.sendto(pkt)  # remote_addr already bound in transport
            logger.debug(f"{prefix}Created transport to {host}:{port} ssrc={ssrc} seq={seq} timestamp={timestamp}")

        samples_per_packet = int(round(target_sr * (chunk_ms / 1000.0)))
        bytes_per_sample = 1 if codec_norm == "pcmu" else 2
        frame_bytes = samples_per_packet * bytes_per_sample
        max_payload = 1400
        if frame_bytes > max_payload:
            frame_bytes = max_payload

        # warmup silent packets
        if warmup_packets and warmup_packets > 0:
            try:
                if codec_norm == "pcmu":
                    silence_lin = (b'\x00\x00' * samples_per_packet)
                    silence_payload = audioop.lin2ulaw(silence_lin, 2)
                else:
                    silence_payload = (b'\x00\x00' * samples_per_packet)
                logger.debug(f"{prefix}Sending {warmup_packets} warmup packets to {host}:{port} codec={codec_norm} payload_type={payload_type} frame_bytes={frame_bytes}")
                for i in range(warmup_packets):
                    header = _build_rtp_header(seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc, int(payload_type), 0)
                    packet = header + (silence_payload[:frame_bytes])
                    send_func(packet)
                    seq = (seq + 1) & 0xFFFF
                    timestamp = (timestamp + samples_per_packet) & 0xFFFFFFFF
                    await asyncio.sleep(min(0.02, chunk_ms / 1000.0))
                logger.info(f"{prefix}warmup sent {warmup_packets} packets to {host}:{port}")
            except Exception:
                logger.exception(prefix + "warmup sending failed but continuing")

        buffer = b""
        packet_count = 0
        first_send_logged = False

        async for audio_part, sr in async_gen:
            try:
                arr = np.asarray(audio_part, dtype=np.float32)
            except Exception:
                logger.exception(prefix + "received non-numpy audio part, skipping")
                continue
            arr = _ensure_mono(arr)
            if int(sr) != target_sr:
                arr = _resample_linear(arr, int(sr), target_sr)
            linear16 = _float_to_int16_bytes(arr)

            if codec_norm == "pcmu":
                try:
                    ulaw_bytes = audioop.lin2ulaw(linear16, 2)
                except Exception:
                    logger.exception(prefix + "audioop.lin2ulaw failed")
                    ulaw_bytes = linear16[::2]
                buffer += ulaw_bytes
            else:
                buffer += linear16

            while len(buffer) >= frame_bytes:
                payload = buffer[:frame_bytes]
                buffer = buffer[frame_bytes:]

                if not first_send_logged:
                    logger.info(f"{prefix}Start sending RTP to {host}:{port} codec={codec_norm} payload_type={payload_type} frame_bytes={frame_bytes} samples_per_packet={samples_per_packet}")
                    first_send_logged = True

                header = _build_rtp_header(seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc, int(payload_type), 0)
                packet = header + payload
                try:
                    send_func(packet)
                except Exception:
                    logger.exception(prefix + "transport.sendto failed")
                seq = (seq + 1) & 0xFFFF
                timestamp = (timestamp + samples_per_packet) & 0xFFFFFFFF
                packet_count += 1
                if realtime:
                    await asyncio.sleep(chunk_ms / 1000.0)

        # final buffer as marker=1
        if len(buffer) > 0:
            header = _build_rtp_header(seq & 0xFFFF, timestamp & 0xFFFFFFFF, ssrc, int(payload_type), 1)
            try:
                send_func(header + buffer)
            except Exception:
                logger.exception(prefix + "transport.sendto failed for final packet")
            packet_count += 1

        logger.info(f"{prefix}Stream finished to {host}:{port}, packets={packet_count}")
        # return final state so caller can persist seq/timestamp/ssrc
        return {"final_seq": seq, "final_timestamp": timestamp, "ssrc": ssrc}
    except asyncio.CancelledError:
        logger.info(prefix + "streaming task cancelled")
        raise
    except Exception:
        logger.exception(prefix + "streaming failed")
        raise
    finally:
        if created_transport is not None:
            try:
                created_transport.close()
            except Exception:
                pass