"""
Usage:
1.
    Install uv from https://docs.astral.sh/uv/getting-started/installation
2.
    Copy this file to new folder
3.
    Download these files
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
4. Run
    uv venv --seed -p 3.12
    source .venv/bin/activate
    uv pip install -U kokoro-onnx soundfile 'misaki[en]'
    uv run main.py

For other languages read https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
"""

import os
import logging
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
import soundfile as sf
from misaki import en, espeak
from kokoro_onnx import Kokoro
import tempfile

# 修复相对导入问题
from download_deps import check_and_download_dependencies, ensure_dir_exists

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
    logging.info("'other' FastAPI 应用启动，开始检查和下载依赖文件...")
    ensure_dir_exists(MODELS_DIR)
    ensure_dir_exists(AUDIO_OUTPUT_DIR)

    if not check_and_download_dependencies():
        logging.error("'other' 模型依赖文件未能成功准备，应用可能无法正常处理请求。")
    else:
        logging.info("'other' 模型依赖文件已就绪，开始加载模型...")
        try:
            model_path = os.path.join(MODELS_DIR, "kokoro-v1.0.onnx")
            voices_path = os.path.join(MODELS_DIR, "voices-v1.0.bin")
            
            if not (os.path.exists(model_path) and os.path.exists(voices_path)):
                logging.error(f"一个或多个 'other' 模型文件在 {MODELS_DIR} 中缺失，无法加载模型。")
                return

            kokoro_model = Kokoro(model_path, voices_path) # vocab_config is not used for v1.0 based on original script
            
            # English G2P with espeak-ng fallback (from original src/other/main.py)
            fallback = espeak.EspeakFallback(british=False)
            g2p_converter = en.G2P(trf=False, british=False, fallback=fallback)
            logging.info("'other' (English) Kokoro 模型和 G2P 转换器加载成功。")
        except Exception as e:
            logging.exception(f"加载 'other' 模型或 G2P 转换器失败: {e}")

@app.post("/generate-speech/") # Keeping the endpoint same for this self-contained app
async def generate_speech_api(
    text: str = Body(..., description="要转换为语音的文本 (英文)"),
    voice: str = Body(..., description="使用的声音模型 (例如 'af_heart' for v1.0 model)"),
    filename: str = Body(None, description="可选，生成的语音文件名（不含路径和后缀，默认为临时文件）"),
    speed: float = Body(1.0, description="语音速度，支持小数，默认为1.0")
):
    if not kokoro_model or not g2p_converter:
        raise HTTPException(status_code=503, detail="'other' 模型服务尚未准备好，请稍后再试或检查启动日志。")

    try:
        logging.info(f"收到 'other' 请求：text='{text}', voice='{voice}', filename='{filename}', speed='{speed}'")
        
        # 规范化speed参数，确保是一个小数位
        speed = round(float(speed), 1)
        
        phonemes, _ = g2p_converter(text)
        samples, sample_rate = kokoro_model.create(phonemes, voice=voice, speed=speed, is_phonemes=True)
        
        ensure_dir_exists(AUDIO_OUTPUT_DIR)

        if filename:
            safe_filename = "".join(c for c in filename if c.isalnum() or c in ('_', '-')).rstrip()
            if not safe_filename:
                safe_filename = "generated_audio_other"
            output_path = os.path.join(AUDIO_OUTPUT_DIR, f"{safe_filename}.wav")
        else:
            fd, output_path = tempfile.mkstemp(suffix=".wav", dir=BASE_DIR)
            os.close(fd)

        sf.write(output_path, samples, sample_rate)
        logging.info(f"'other' 语音文件已生成: {output_path}")
        
        return FileResponse(output_path, media_type='audio/wav', filename=os.path.basename(output_path))
    
    except Exception as e:
        logging.exception(f"'other' 语音合成失败: {e}")
        raise HTTPException(status_code=500, detail=f"'other' 语音合成失败: {str(e)}")

if __name__ == "__main__":
    ensure_dir_exists(MODELS_DIR)
    ensure_dir_exists(AUDIO_OUTPUT_DIR)

    if check_and_download_dependencies():
        model_file_path = os.path.join(MODELS_DIR, "kokoro-v1.0.onnx")
        voices_file_path = os.path.join(MODELS_DIR, "voices-v1.0.bin")
        
        if not (os.path.exists(model_file_path) and os.path.exists(voices_file_path)):
            logging.error(f"关键 'other' 模型文件在 {MODELS_DIR} 中缺失，无法启动服务。")
        else:
            if not kokoro_model or not g2p_converter:
                 kokoro_model = Kokoro(model_file_path, voices_file_path)
                 fallback = espeak.EspeakFallback(british=False)
                 g2p_converter = en.G2P(trf=False, british=False, fallback=fallback)
                 logging.info("'other' 模型在 __main__ 中加载成功 (用于直接运行测试)。")
            uvicorn.run(app, host="0.0.0.0", port=8211) # Running on a different port (e.g., 8001) to avoid conflict with chinese app
    else:
        logging.error("'other' 依赖下载失败，FastAPI 服务无法启动。")

# 示例 curl 请求 (针对 port 8211):
# curl -X POST "http://localhost:8211/generate-speech/" -H "Content-Type: application/json" -d '{"text":"Hello world, this is a test.", "voice":"en-us-kathleen-low", "filename":"hello_other", "speed": 1.0}' --output src/other/generated_audio/hello_other_output.wav
# (Note: 'en-us-kathleen-low' is an example voice for v1.0, check model documentation for available voices like 'af_heart')