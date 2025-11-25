"""
# Note: this file is a modified version of the repository's src/chinese/main.py.
# 改动要点：
# - 每个 uuid（user_uuid）拥有一个持久化的 UDP transport + SSRC + seq + timestamp 上下文（uuid_contexts）。
# - 在 uuid 的 worker 中，处理每个 job 时复用该 transport/ssrc/seq/timestamp（避免软电话忽略后续流）。
# - stream_rtp_from_asyncgen 支持 reuse_transport 模式并返回 final seq/timestamp/ssrc，用于更新上下文。
# - clear_msg / 按 uuid 清理时会取消正在运行任务、移除排队任务并关闭该 uuid 的 transport（以重置上下文）。
# - 新增：在收到请求时记录本机时区格式的时间（received_local）并写入 job.meta；
#         在开始发送语音时记录本机时区格式的时间（send_local）、uuid、text，并计算并记录两者的时间间隔（秒）。
"""

import os
import sys
import pathlib

# Ensure src is on sys.path before importing local modules
SRC_DIR = str(pathlib.Path(__file__).resolve().parents[1])
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import numpy as np
# 1. 先拿到原函数
_load = np.load
# 2. 再包一层，只改 allow_pickle
np.load = lambda *a, **k: _load(*a, **{**k, "allow_pickle": True})

import logging
import uvicorn
import uuid
import asyncio
import random
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import JSONResponse
import inspect

from misaki import zh
from kokoro_onnx import Kokoro
from download_deps import check_and_download_dependencies, ensure_dir_exists
from cache import check_audio_cache

# stream sender
from utils.stream_rtp_streaming import stream_rtp_from_asyncgen

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
#MODELS_DIR = os.path.join(BASE_DIR, "models")
MODELS_DIR = "/home/liuzhongping/kokoro-82M-zh-en-V1_1"
AUDIO_OUTPUT_DIR = os.path.join(BASE_DIR, "generated_audio")

app = FastAPI()

kokoro_model: Optional[Kokoro] = None
g2p_converter = None

# Task / queue management data structures
# active_stream_tasks: taskid -> 'queued' | asyncio.Task (running)
active_stream_tasks: Dict[str, Any] = {}
# active_stream_meta: taskid -> metadata dict (user_uuid, target_host, target_port, ...)
active_stream_meta: Dict[str, Dict[str, Any]] = {}
# completed_results: taskid -> result dict for finished tasks (status/result/exception)
completed_results: Dict[str, Dict[str, Any]] = {}

# uuid -> per-uuid queue object (see class PerUuidQueue)
uuid_queues: Dict[str, "PerUuidQueue"] = {}
# uuid -> worker asyncio.Task
uuid_workers: Dict[str, asyncio.Task] = {}
# uuid -> persistent context: transport, ssrc, seq, timestamp
uuid_contexts: Dict[str, Dict[str, Any]] = {}

# locks to protect context creation
uuid_context_locks: Dict[str, asyncio.Lock] = {}
uuid_contexts_lock = asyncio.Lock()

# lock to protect the above maps
active_tasks_lock = asyncio.Lock()


class PerUuidQueue:
    """
    Minimal async queue with ability to remove by taskid and clear all.
    """

    def __init__(self):
        from collections import deque
        self._dq = deque()
        self._cv = asyncio.Condition()

    async def put(self, job: dict):
        async with self._cv:
            self._dq.append(job)
            self._cv.notify()

    async def get(self) -> dict:
        async with self._cv:
            while not self._dq:
                await self._cv.wait()
            return self._dq.popleft()

    def remove_by_taskid(self, taskid: str) -> bool:
        removed = False
        for idx, job in enumerate(list(self._dq)):
            if job.get("taskid") == taskid:
                del self._dq[idx]
                removed = True
                break
        return removed

    async def qsize(self) -> int:
        async with self._cv:
            return len(self._dq)

    def clear_all(self) -> list:
        """
        Synchronously remove and return all queued jobs.
        Safe to call in asyncio single-threaded context.
        """
        items = list(self._dq)
        self._dq.clear()
        # best-effort notify to unstick waiters
        try:
            async def _notify():
                async with self._cv:
                    self._cv.notify_all()
            asyncio.get_running_loop().create_task(_notify())
        except Exception:
            pass
        return items


async def _ensure_uuid_context_and_worker(user_uuid: str, ssrc: int) -> None:
    """
    Ensure queue, context and worker exist for user_uuid.
    This version uses a per-uuid asyncio.Lock to avoid concurrent duplicate context creation.
    """
    if user_uuid is None:
        user_uuid = "__task_unknown__"

    # Ensure queue exists (no heavy synchronization needed)
    if user_uuid not in uuid_queues:
        uuid_queues[user_uuid] = PerUuidQueue()

    # Ensure there is a per-uuid lock (create under global lock to avoid races creating locks)
    async with uuid_contexts_lock:
        lock = uuid_context_locks.get(user_uuid)
        if lock is None:
            lock = asyncio.Lock()
            uuid_context_locks[user_uuid] = lock

    # Acquire per-uuid lock to serialize context creation
    async with lock:
        # Double-checked: another coroutine may have created context while we waited for the lock
        if user_uuid not in uuid_contexts:
            loop = asyncio.get_running_loop()
            try:
                transport, protocol = await loop.create_datagram_endpoint(
                    lambda: asyncio.DatagramProtocol(),
                    local_addr=('0.0.0.0', 0)
                )
                sockname = transport.get_extra_info('sockname')  # (ip, port)
                logger.info(f"[context] created transport for uuid={user_uuid} local_sock={sockname}")
                ctx = {
                    "transport": transport,
                    "ssrc": ssrc,
                    "seq": random.randint(0, 0xFFFF),
                    "timestamp": random.randint(0, 0x7FFFFFFF),
                }
                uuid_contexts[user_uuid] = ctx
            except Exception:
                logger.exception(f"[context] failed creating transport for uuid={user_uuid}")
                # Fallback context without transport
                uuid_contexts[user_uuid] = {"transport": None, "ssrc": ssrc, "seq": random.randint(0, 0xFFFF), "timestamp": random.randint(0, 0x7FFFFFFF)}

    # Start worker if needed.
    if user_uuid not in uuid_workers or uuid_workers[user_uuid].done():
        worker_task = asyncio.create_task(_uuid_worker_loop(user_uuid))
        uuid_workers[user_uuid] = worker_task
        logger.info(f"[queue] started worker for uuid={user_uuid}")


async def _uuid_worker_loop(user_uuid: str):
    """
    Worker that processes jobs sequentially for a given user_uuid.
    Uses uuid_contexts[user_uuid] to persist transport/ssrc/seq/timestamp.
    """
    queue = uuid_queues[user_uuid]
    logger.info(f"[queue] worker running for uuid={user_uuid}")
    try:
        while True:
            job = await queue.get()
            taskid = job["taskid"]
            # mark queued -> now starting
            async with active_tasks_lock:
                if active_stream_tasks.get(taskid) == "queued":
                    active_stream_tasks[taskid] = None
                else:
                    logger.info(f"[queue] job {taskid} not active when popped (maybe cancelled); skip")
                    active_stream_meta.pop(taskid, None)
                    continue

            # create processing task
            process_task = asyncio.create_task(_process_job(job))
            async with active_tasks_lock:
                active_stream_tasks[taskid] = process_task

            try:
                # pass through context so _process_job can update it
                result = await process_task
                completed_results[taskid] = {"status": "done", "result": str(result)}
                logger.info(f"[queue] job {taskid} done (uuid={user_uuid})")
            except asyncio.CancelledError:
                completed_results[taskid] = {"status": "cancelled"}
                logger.info(f"[queue] job {taskid} cancelled (uuid={user_uuid})")
            except Exception as e:
                completed_results[taskid] = {"status": "done_with_exception", "exception": str(e)}
                logger.exception(f"[queue] job {taskid} failed: {e}")
            finally:
                async with active_tasks_lock:
                    active_stream_tasks.pop(taskid, None)
                    active_stream_meta.pop(taskid, None)
            # continue loop
    except asyncio.CancelledError:
        logger.info(f"[queue] worker for uuid={user_uuid} cancelled")
        # drain and mark remaining as cancelled
        try:
            while True:
                job = uuid_queues[user_uuid]._dq.popleft()
                tid = job.get("taskid")
                completed_results[tid] = {"status": "cancelled"}
                async with active_tasks_lock:
                    active_stream_tasks.pop(tid, None)
                    active_stream_meta.pop(tid, None)
        except Exception:
            pass
        raise
    except Exception:
        logger.exception(f"[queue] worker for uuid={user_uuid} terminated with exception")
        raise


async def _process_job(job: dict):
    """
    Process a single job: call stream_rtp_from_asyncgen using the uuid persistent context if present.
    After streaming, update uuid_contexts with final seq/timestamp so next job continues smoothly.
    Also log request receive time, start-sending time, uuid, text and interval between receive and send.
    """
    taskid = job["taskid"]
    user_uuid = job.get("user_uuid")
    stream_gen = job["stream_gen"]
    target_host = job["target_host"]
    target_port = job["target_port"]
    chunk_ms = int(job.get("chunk_ms", 20))
    codec = job.get("codec", "l16")
    target_sr = int(job.get("target_sr", 8000))
    logger_prefix = job.get("logger_prefix", "")

    # extract meta info (received_at, received_local, text)
    meta = job.get("meta", {}) or {}
    received_at = meta.get("received_at")  # epoch seconds float
    received_local = meta.get("received_local")  # local formatted string
    req_text = meta.get("text", "")  # original text

    # determine context for this uuid (may be None)
    ctx = None
    if user_uuid is None:
        key = f"__task__:{taskid}"
        ctx = uuid_contexts.get(key)
    else:
        ctx = uuid_contexts.get(user_uuid)

    # prepare params for reuse transport
    reuse_transport = False
    transport = None
    initial_ssrc = None
    initial_seq = None
    initial_timestamp = None

    if ctx:
        transport = ctx.get("transport")
        initial_ssrc = ctx.get("ssrc")
        initial_seq = ctx.get("seq")
        initial_timestamp = ctx.get("timestamp")
        if transport is not None:
            reuse_transport = True

    # Log start-send info: local time, uuid, text, and delta from receive
    try:
        start_send_epoch = time.time()
        # local time with computer's timezone
        local_dt = datetime.now().astimezone()
        start_local = local_dt.strftime("%Y-%m-%d %H:%M:%S %Z%z")
        delta_s = None
        if isinstance(received_at, (int, float)):
            delta_s = start_send_epoch - float(received_at)
        # truncate text for logging to avoid huge logs
        display_text = (req_text[:300] + '...') if isinstance(req_text, str) and len(req_text) > 300 else req_text
        logger.info(f"[send-start] time={start_local} uuid={user_uuid} taskid={taskid} text=\"{display_text}\" delay_s={delta_s}")
    except Exception:
        logger.exception(f"[process_job] failed logging start-send info for task {taskid}")

    try:
        _call_kwargs = {
            "realtime": True,
            "chunk_ms": chunk_ms,
            "target_sr": target_sr,
            "codec": codec,
            "payload_type": None,
            "logger_prefix": logger_prefix,
            "reuse_transport": reuse_transport,
            "transport": transport,
            "initial_ssrc": initial_ssrc,
            "initial_seq": initial_seq,
            "initial_timestamp": initial_timestamp,
        }

        # inspect target function signature and filter keys
        try:
            sig = inspect.signature(stream_rtp_from_asyncgen)
            supported = set(sig.parameters.keys())
            filtered_kwargs = {k: v for k, v in _call_kwargs.items() if k in supported}
            removed = [k for k in _call_kwargs.keys() if k not in supported]
            if removed:
                logger.debug(f"[compat] filtered unsupported kwargs for stream_rtp_from_asyncgen: {removed}")
            # positional args: host, port, async_gen
            res = await stream_rtp_from_asyncgen(target_host, target_port, stream_gen, **filtered_kwargs)
        except Exception as e:
            logger.exception(f"[process_job] calling stream_rtp_from_asyncgen failed: {e}")
            raise

        # res expected to be dict with final_seq, final_timestamp, ssrc
        if isinstance(res, dict) and ctx is not None:
            # update ctx with returned values to keep continuity
            ctx['ssrc'] = res.get('ssrc', ctx.get('ssrc'))
            ctx['seq'] = res.get('final_seq', ctx.get('seq'))
            ctx['timestamp'] = res.get('final_timestamp', ctx.get('timestamp'))
        return {"taskid": taskid, "status": "stream_finished"}
    except asyncio.CancelledError:
        # try to close generator
        try:
            await stream_gen.aclose()
        except Exception:
            pass
        raise
    except Exception:
        logger.exception(f"[process_job] streaming failed for task {taskid}")
        raise


async def _enqueue_job_for_uuid(user_uuid: str, job: dict):
    """
    Add job into the uuid queue (create queue/worker/context if needed).
    """
    if user_uuid is None:
        user_uuid = f"__task__:{job['taskid']}"

    # ensure context and worker; pass job["ssrc"] so context uses same ssrc baseline
    await _ensure_uuid_context_and_worker(user_uuid, int(job.get("ssrc", random.getrandbits(32))))
    async with active_tasks_lock:
        active_stream_tasks[job["taskid"]] = "queued"
        active_stream_meta[job["taskid"]] = job.get("meta", {})
    await uuid_queues[user_uuid].put(job)
    logger.info(f"[enqueue] task {job['taskid']} enqueued to uuid={user_uuid}")


async def _clear_queue_and_cancel(user_uuid: Optional[str]) -> Dict[str, int]:
    """
    Clear queued and running jobs belonging to the given user_uuid and close transport context.
    Returns counts.
    """
    if user_uuid is None:
        return {"queued_removed": 0, "running_cancelled": 0}

    queue_key = user_uuid
    queued_removed = 0
    running_cancelled = 0

    # Remove queued jobs
    q = uuid_queues.get(queue_key)
    if q:
        try:
            items = q.clear_all()
        except Exception:
            items = []
            try:
                while True:
                    items.append(q._dq.popleft())
            except Exception:
                pass
        for job in items:
            tid = job.get("taskid")
            queued_removed += 1
            completed_results[tid] = {"status": "cancelled_by_clear"}
            async with active_tasks_lock:
                active_stream_tasks.pop(tid, None)
                active_stream_meta.pop(tid, None)

    # Cancel running tasks of this uuid
    async with active_tasks_lock:
        to_cancel = [tid for tid, meta in active_stream_meta.items() if meta.get("user_uuid") == user_uuid]
        for tid in to_cancel:
            entry = active_stream_tasks.get(tid)
            if isinstance(entry, asyncio.Task):
                try:
                    entry.cancel()
                    running_cancelled += 1
                    completed_results[tid] = {"status": "cancelled_by_clear"}
                except Exception:
                    logger.exception(f"[clear] failed to cancel running task {tid}")

    # # Close and remove context (so next job gets fresh transport/ssrc/seq/timestamp)
    # ctx = uuid_contexts.pop(queue_key, None)
    # if ctx:
    #     try:
    #         tr = ctx.get("transport")
    #         if tr:
    #             tr.close()
    #             logger.info(f"[clear] closed transport for uuid={queue_key}")
    #     except Exception:
    #         logger.exception(f"[clear] failed closing transport for uuid={queue_key}")

    # # Also remove and cleanup the per-uuid lock if present
    # async with uuid_contexts_lock:
    #     uuid_context_locks.pop(queue_key, None)

    logger.info(f"[clear] for uuid={queue_key} removed queued={queued_removed} cancelled running~={running_cancelled}")
    return {"queued_removed": queued_removed, "running_cancelled": running_cancelled}

async def _cancel_task_by_taskid(taskid: str, wait_seconds: float = 3.0) -> dict:
    async with active_tasks_lock:
        entry = active_stream_tasks.get(taskid)
        meta = active_stream_meta.get(taskid, {})
    if entry is None:
        if taskid in completed_results:
            status = completed_results[taskid].get("status")
            return {"taskid": taskid, "found": False, "cancel_requested": False, "still_exists": False, "message": f"already {status}"}
        return {"taskid": taskid, "found": False, "cancel_requested": False, "still_exists": False}

    # queued -> try remove
    if entry == "queued":
        user_uuid = meta.get("user_uuid")
        queue_key = user_uuid if user_uuid is not None else f"__task__:{taskid}"
        q = uuid_queues.get(queue_key)
        removed = False
        if q:
            removed = q.remove_by_taskid(taskid)
        if removed:
            async with active_tasks_lock:
                active_stream_tasks.pop(taskid, None)
                active_stream_meta.pop(taskid, None)
                completed_results[taskid] = {"status": "cancelled"}
            logger.info(f"[cancel] removed queued task {taskid} from queue {queue_key}")
            return {"taskid": taskid, "found": True, "cancel_requested": True, "still_exists": False, "cancelled_immediate": True}

    # running -> cancel
    if isinstance(entry, asyncio.Task):
        task = entry
        try:
            task.cancel()
            cancelled_immediate = False
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=wait_seconds)
            except asyncio.TimeoutError:
                logger.info(f"Cancellation of task {taskid} timed out (task may still be running)")
            except asyncio.CancelledError:
                cancelled_immediate = True
            except Exception:
                pass
            async with active_tasks_lock:
                still_exists = taskid in active_stream_tasks
            return {"taskid": taskid, "found": True, "cancel_requested": True, "still_exists": still_exists, "cancelled_immediate": cancelled_immediate}
        except Exception:
            logger.exception(f"Failed to cancel task {taskid}")
            return {"taskid": taskid, "found": True, "cancel_requested": True, "still_exists": True, "cancelled_immediate": False}

    return {"taskid": taskid, "found": True, "cancel_requested": False, "still_exists": True}


@app.on_event("startup")
async def startup_event():
    global kokoro_model, g2p_converter
    logging.info("FastAPI 应用启动，开始检查和下载依赖文件...")
    ensure_dir_exists(MODELS_DIR)
    ensure_dir_exists(AUDIO_OUTPUT_DIR)

    if not check_and_download_dependencies():
        logging.error("依赖文件未能成功准备，应用可能无法正常处理请求。")
    else:
        logging.info("依赖文件已就绪，开始加载模型...")
        try:
            # model_path = os.path.join(MODELS_DIR, "kokoro-v1.1-zh.onnx")
            # voices_path = os.path.join(MODELS_DIR, "voices-v1.1-zh.bin")
            # config_path = os.path.join(MODELS_DIR, "config.json")
            model_path = os.path.join(MODELS_DIR, "model.onnx")
            voices_path = os.path.join(MODELS_DIR, "zf_001.npy")
            config_path = os.path.join(MODELS_DIR, "conf.json")

            if not (os.path.exists(model_path) and os.path.exists(voices_path) and os.path.exists(config_path)):
                logging.error(f"一个或多个模型文件在 {MODELS_DIR} 中缺失，无法加载模型。")
                return
            kokoro_model = Kokoro(model_path, voices_path, vocab_config=config_path)
            g2p_converter = zh.ZHG2P(version="1.1")
            logging.info("Kokoro 模型和 G2P 转换器加载成功。")
        except Exception as e:
            logging.exception(f"加载模型或 G2P 转换器失败: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    # cancel workers
    logger.info("[shutdown] cancelling uuid workers and running tasks")
    for uid, w in list(uuid_workers.items()):
        try:
            w.cancel()
        except Exception:
            pass
    # cancel running tasks
    async with active_tasks_lock:
        tasks = [t for t in active_stream_tasks.values() if isinstance(t, asyncio.Task)]
    for t in tasks:
        try:
            t.cancel()
        except Exception:
            pass
    # close transports
    for uid, ctx in list(uuid_contexts.items()):
        try:
            tr = ctx.get("transport")
            if tr:
                tr.close()
                logger.info(f"[shutdown] closed transport for uuid={uid}")
        except Exception:
            pass


@app.post("/stream-rtp-streaming/")
async def stream_rtp_streaming_endpoint(
    text: str = Body(..., description="要转换为语音的文本"),
    voice: str = Body(..., description="声音，例如 'zf_001'"),
    target_host: str = Body(..., description="接收 RTP 的目标 IP"),
    target_port: int = Body(..., description="接收 RTP 的目标 UDP 端口"),
    speed: float = Body(1.0, description="语速"),
    chunk_ms: int = Body(20, description="每个 RTP 包对应的毫秒数（默认20ms）"),
    ssrc: int = Body(None, description="可选：指定包的初始ssrc"),
    codec: str = Body("pcmu", description="编码：'pcmu' 或 'l16'（默认 pcmu）"),
    taskid: str = Body(None, description="可选：指定用于管理该推流任务的 taskid（UUID 字符串），若为空服务端会生成"),
    uuid_param: str = Body(None, description="可选：业务层 UUID，允许多次调用用相同 uuid_param 以便后续按 uuid 取消所有相关任务"),
    clear_msg: bool = Body(False, description="是否在将请求放入队列前清除 uuid_param 所在队列的未执行或未执行完毕任务；默认 False")
):
    """
    接收请求并将工作放入以 uuid_param 为键的队列，队列内顺序执行。
    clear_msg=True 时会先删除/取消该 uuid_param 队列中未执行或未执行完毕的任务（并关闭该 uuid 的 transport，上下文重建在下次入队时）。
    """
    global kokoro_model, g2p_converter
    if not kokoro_model or not g2p_converter:
        raise HTTPException(status_code=503, detail="模型服务尚未准备好")

    try:
        speed = round(float(speed), 1)
    except Exception:
        raise HTTPException(status_code=400, detail="speed 参数无效")

    # taskid 校验或生成
    if taskid:
        try:
            uuid_obj = uuid.UUID(taskid)
            taskid_str = str(uuid_obj)
        except Exception:
            raise HTTPException(status_code=400, detail="taskid 必须是有效的 UUID 字符串")
    else:
        taskid_str = str(uuid.uuid4())

    # uuid_param 校验
    user_uuid = None
    if uuid_param is not None:
        if isinstance(uuid_param, str) and uuid_param.strip() != "":
            user_uuid = uuid_param.strip()
        else:
            raise HTTPException(status_code=400, detail="uuid_param 若提供必须为非空字符串")

    async with active_tasks_lock:
        if taskid_str in active_stream_tasks:
            raise HTTPException(status_code=409, detail=f"taskid {taskid_str} 已存在（可能正在运行或已排队）")

    # 如果请求要求先清除 uuid 队列，则执行清理
    if clear_msg:
        cleared = await _clear_queue_and_cancel(user_uuid)
        logger.info(f"[stream-request] clear_msg requested for uuid={user_uuid}: {cleared}")

    # g2p
    try:
        phonemes, _ = g2p_converter(text)
    except Exception as e:
        logging.exception("g2p conversion failed")
        raise HTTPException(status_code=500, detail=f"g2p 转换失败: {e}")

    # create_stream 返回异步生成器（延迟生成，直到消费）
    try:
        stream_gen = kokoro_model.create_stream(phonemes, voice=voice, speed=speed, is_phonemes=True)
    except Exception as e:
        logging.exception("create_stream failed")
        raise HTTPException(status_code=500, detail=f"无法创建流: {e}")

    if ssrc is None:
        ssrc = random.getrandbits(32)

    # prepare job dict, include meta received_at and text for logging/delay measurement
    received_ts = time.time()
    # local time formatted with computer timezone
    received_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z%z")
    job_meta = {"user_uuid": user_uuid, "target_host": target_host, "target_port": int(target_port),
                "received_at": received_ts, "received_local": received_local, "text": text}
    job = {
        "taskid": taskid_str,
        "user_uuid": user_uuid,
        "stream_gen": stream_gen,
        "target_host": target_host,
        "target_port": int(target_port),
        "chunk_ms": int(chunk_ms),
        "ssrc": int(ssrc),
        "codec": codec.lower() if isinstance(codec, str) else "pcmu",
        "target_sr": 8000,
        "logger_prefix": f"{target_host}:{target_port}",
        "meta": job_meta
    }

    # log request receipt (local time, uuid, taskid, text)
    try:
        display_text = (text[:300] + '...') if isinstance(text, str) and len(text) > 300 else text
        logger.info(f"[request-received] time={received_local} uuid={user_uuid} taskid={taskid_str} text=\"{display_text}\"")
    except Exception:
        logger.exception("[request-received] failed to log request")

    # enqueue job into the per-uuid queue
    await _enqueue_job_for_uuid(user_uuid, job)

    return JSONResponse({"status": "ok", "taskid": taskid_str, "uuid": user_uuid})


@app.post("/stream-cancel/{taskid}")
async def stream_cancel(taskid: str):
    """
    取消指定 taskid 的推流任务（若存在）。
    """
    res = await _cancel_task_by_taskid(taskid)
    if not res["found"]:
        return JSONResponse({"status": "not_found", "taskid": taskid, "message": "任务不存在或已结束"}, status_code=404)
    return JSONResponse({"status": "cancel_requested", **res})


@app.post("/stream-cancel-by-uuid/{user_uuid}")
async def stream_cancel_by_uuid(user_uuid: str):
    """
    根据提供的业务 uuid（user_uuid）取消所有未完成且 meta.user_uuid == user_uuid 的任务，并关闭对应 transport。
    """
    if not user_uuid or not isinstance(user_uuid, str):
        raise HTTPException(status_code=400, detail="user_uuid 必须为非空字符串")

    async with active_tasks_lock:
        matching = [tid for tid, meta in active_stream_meta.items() if meta.get("user_uuid") == user_uuid and tid in active_stream_tasks]

    if not matching:
        return JSONResponse({"status": "not_found", "user_uuid": user_uuid, "matched_taskids": [], "message": "未找到匹配的运行中/排队任务"}, status_code=404)

    results = []
    for tid in matching:
        res = await _cancel_task_by_taskid(tid)
        results.append(res)

    # close and remove transport context (reset)
    ctx = uuid_contexts.pop(user_uuid, None)
    if ctx:
        try:
            tr = ctx.get("transport")
            if tr:
                tr.close()
                logger.info(f"[cancel-by-uuid] closed transport for uuid={user_uuid}")
        except Exception:
            logger.exception(f"[cancel-by-uuid] failed closing transport for uuid={user_uuid}")

    # also remove per-uuid lock if exists
    async with uuid_contexts_lock:
        uuid_context_locks.pop(user_uuid, None)

    return JSONResponse({"status": "cancel_requested", "user_uuid": user_uuid, "results": results})


@app.get("/stream-status/{taskid}")
async def stream_status(taskid: str):
    """
    查询任务运行状态（按单个 taskid）。
    """
    async with active_tasks_lock:
        entry = active_stream_tasks.get(taskid)
        meta = active_stream_meta.get(taskid)

    if not entry:
        res = completed_results.get(taskid)
        if res:
            return JSONResponse({"status": res.get("status", "done"), "taskid": taskid, "result": res, "meta": meta})
        return JSONResponse({"status": "not_found_or_done", "taskid": taskid, "meta": meta})

    if entry == "queued":
        return JSONResponse({"status": "queued", "taskid": taskid, "meta": meta})
    elif isinstance(entry, asyncio.Task):
        if entry.done():
            try:
                r = entry.result()
                return JSONResponse({"status": "done", "taskid": taskid, "result": str(r), "meta": meta})
            except asyncio.CancelledError:
                return JSONResponse({"status": "cancelled", "taskid": taskid, "meta": meta})
            except Exception as e:
                return JSONResponse({"status": "done_with_exception", "taskid": taskid, "exception": str(e), "meta": meta})
        else:
            return JSONResponse({"status": "running", "taskid": taskid, "meta": meta})
    else:
        return JSONResponse({"status": "unknown", "taskid": taskid, "meta": meta})


if __name__ == "__main__":
    ensure_dir_exists(MODELS_DIR)
    ensure_dir_exists(AUDIO_OUTPUT_DIR)

    if check_and_download_dependencies():
        # model_file_path = os.path.join(MODELS_DIR, "kokoro-v1.1-zh.onnx")
        # voices_file_path = os.path.join(MODELS_DIR, "voices-v1.1-zh.bin")
        # config_file_path = os.path.join(MODELS_DIR, "config.json")
        model_file_path = os.path.join(MODELS_DIR, "model.onnx")
        voices_file_path = os.path.join(MODELS_DIR, "zf_001.npy")
        config_file_path = os.path.join(MODELS_DIR, "conf.json")
        if not (os.path.exists(model_file_path) and os.path.exists(voices_file_path) and os.path.exists(config_file_path)):
            logging.error(f"关键模型文件在 {MODELS_DIR} 中缺失，无法启动服务。请确保依赖已正确下载。")
        else:
            if not kokoro_model or not g2p_converter:
                kokoro_model = Kokoro(model_file_path, voices_file_path, vocab_config=config_file_path)
                g2p_converter = zh.ZHG2P(version="1.1")
                logging.info("模型在 __main__ 中加载成功 (用于直接运行测试)。")
            uvicorn.run(app, host="0.0.0.0", port=8210)