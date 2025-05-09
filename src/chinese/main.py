"""
Usage:
1.
    Install uv from https://docs.astral.sh/uv/getting-started/installation
2.
    Copy this file to new folder
3.
    Run
    uv venv -p 3.12
    uv pip install -U kokoro-onnx soundfile 'misaki[zh]'
3.
    Download these files
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.1-zh.onnx
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.1-zh.bin
    https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/raw/main/config.json
4. Run
    uv run main.py
"""

import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
import soundfile as sf
from misaki import zh
from kokoro_onnx import Kokoro
import tempfile

# 调整导入，并定义新的目录常量
from download_deps import check_and_download_dependencies, ensure_dir_exists
from cache import check_audio_cache

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
AUDIO_OUTPUT_DIR = os.path.join(BASE_DIR, "generated_audio")

app = FastAPI()

# 全局变量用于存储加载的模型和 G2P 转换器
kokoro_model: Kokoro = None
g2p_converter = None

@app.on_event("startup")
async def startup_event():
    global kokoro_model, g2p_converter
    logging.info("FastAPI 应用启动，开始检查和下载依赖文件...")
    ensure_dir_exists(MODELS_DIR) # 确保 models 目录存在
    ensure_dir_exists(AUDIO_OUTPUT_DIR) # 确保 generated_audio 目录存在

    if not check_and_download_dependencies(): # 该函数内部会处理 models 目录的依赖
        logging.error("依赖文件未能成功准备，应用可能无法正常处理请求。")
    else:
        logging.info("依赖文件已就绪，开始加载模型...")
        try:
            model_path = os.path.join(MODELS_DIR, "kokoro-v1.1-zh.onnx")
            voices_path = os.path.join(MODELS_DIR, "voices-v1.1-zh.bin")
            config_path = os.path.join(MODELS_DIR, "config.json")
            
            if not (os.path.exists(model_path) and os.path.exists(voices_path) and os.path.exists(config_path)):
                logging.error(f"一个或多个模型文件在 {MODELS_DIR} 中缺失，无法加载模型。")
                return # 或者抛出异常阻止应用进一步启动

            kokoro_model = Kokoro(model_path, voices_path, vocab_config=config_path)
            g2p_converter = zh.ZHG2P(version="1.1")
            logging.info("Kokoro 模型和 G2P 转换器加载成功。")
        except Exception as e:
            logging.exception(f"加载模型或 G2P 转换器失败: {e}")

@app.post("/generate-speech/")
async def generate_speech_api(
    text: str = Body(..., description="要转换为语音的文本"),
    voice: str = Body(..., description="使用的声音模型，例如 'zf_001'"),
    filename: str = Body(None, description="可选，生成的语音文件名（不含路径和后缀，默认为临时文件）"),
    speed: float = Body(1.0, description="语音速度，支持小数，默认为1.0")
):
    if not kokoro_model or not g2p_converter:
        raise HTTPException(status_code=503, detail="模型服务尚未准备好，请稍后再试或检查启动日志。")

    try:
        logging.info(f"收到请求：text='{text}', voice='{voice}', filename='{filename}', speed='{speed}'")
        
        # 规范化speed参数，确保是一个小数位
        speed = round(float(speed), 1)
        
        # 缓存检查逻辑
        if filename: # 仅当提供了明确的文件名时才检查缓存
            safe_filename_base = "".join(c for c in filename if c.isalnum() or c in ('_', '-')).rstrip()
            if not safe_filename_base: # 如果处理后为空，则不使用缓存逻辑或赋一个默认值（这里选择不使用）
                pass
            else:
                cached_file_path = check_audio_cache(safe_filename_base, AUDIO_OUTPUT_DIR)
                if cached_file_path:
                    logging.info(f"缓存命中：找到文件 {cached_file_path}，直接返回。")
                    return FileResponse(cached_file_path, media_type='audio/wav', filename=os.path.basename(cached_file_path))
                else:
                    logging.info(f"缓存未命中：文件 {safe_filename_base}.wav 在 {AUDIO_OUTPUT_DIR} 中未找到，将进行生成。")

        phonemes, _ = g2p_converter(text)
        samples, sample_rate = kokoro_model.create(phonemes, voice=voice, speed=speed, is_phonemes=True)
        
        ensure_dir_exists(AUDIO_OUTPUT_DIR) # 确保输出目录存在

        if filename:
            safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-')).rstrip()
            if not safe_filename:
                safe_filename = "generated_audio" # Fallback if filename becomes empty after sanitizing
            # 文件保存到 AUDIO_OUTPUT_DIR
            output_path = os.path.join(AUDIO_OUTPUT_DIR, f"{safe_filename}.wav")
        else:
            # 临时文件仍在 BASE_DIR (chinese/) 下创建，或可指定 AUDIO_OUTPUT_DIR
            fd, output_path = tempfile.mkstemp(suffix=".wav", dir=BASE_DIR)
            # 若希望临时文件也在 generated_audio 目录：
            # fd, output_path = tempfile.mkstemp(suffix=".wav", dir=AUDIO_OUTPUT_DIR)
            os.close(fd) 

        sf.write(output_path, samples, sample_rate)
        logging.info(f"语音文件已生成: {output_path}")
        
        return FileResponse(output_path, media_type='audio/wav', filename=os.path.basename(output_path))
    
    except Exception as e:
        logging.exception(f"语音合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"语音合成失败: {str(e)}")

if __name__ == "__main__":
    ensure_dir_exists(MODELS_DIR)
    ensure_dir_exists(AUDIO_OUTPUT_DIR)

    if check_and_download_dependencies():
        model_file_path = os.path.join(MODELS_DIR, "kokoro-v1.1-zh.onnx")
        voices_file_path = os.path.join(MODELS_DIR, "voices-v1.1-zh.bin")
        config_file_path = os.path.join(MODELS_DIR, "config.json")
        
        if not (os.path.exists(model_file_path) and os.path.exists(voices_file_path) and os.path.exists(config_file_path)):
            logging.error(f"关键模型文件在 {MODELS_DIR} 中缺失，无法启动服务。请确保依赖已正确下载。")
        else:
            if not kokoro_model or not g2p_converter: # 确保模型只加载一次
                 kokoro_model = Kokoro(model_file_path, voices_file_path, vocab_config=config_file_path)
                 g2p_converter = zh.ZHG2P(version="1.1")
                 logging.info("模型在 __main__ 中加载成功 (用于直接运行测试)。")
            uvicorn.run(app, host="0.0.0.0", port=8210)
    else:
        logging.error("依赖下载失败，FastAPI 服务无法启动。")

# 示例 curl 请求 (路径和之前一样，因为 FastAPI 处理的是端点):
# curl -X POST "http://localhost:8000/generate-speech/" -H "Content-Type: application/json" -d '{"text":"你好，世界！", "voice":"zf_001", "filename":"hello_world"}' --output chinese/generated_audio/hello_world_output.wav
# (注意：如果使用 --output，客户端需要指定完整或相对的保存路径。服务器端行为是固定的。)