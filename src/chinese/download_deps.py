import os
import requests
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")

# 中文模型依赖文件及其下载链接
CHINESE_DEPENDENCIES = {
    "kokoro-v1.1-zh.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.1-zh.onnx",
    "voices-v1.1-zh.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.1-zh.bin",
    "config.json": "https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/raw/main/config.json"
}

# 英文模型依赖文件及其下载链接（用于中英混合TTS）
ENGLISH_DEPENDENCIES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
}

# 兼容旧代码的 DEPENDENCIES 变量（仅包含中文模型）
DEPENDENCIES = CHINESE_DEPENDENCIES

def ensure_dir_exists(directory_path):
    """确保目录存在，如果不存在则创建"""
    if not os.path.exists(directory_path):
        logging.info(f"目录 {directory_path} 不存在，正在创建...")
        os.makedirs(directory_path)
        logging.info(f"目录 {directory_path} 创建成功。")

def download_file(url, local_filename):
    """下载文件并保存到本地的 models 目录"""
    ensure_dir_exists(MODELS_DIR) # 确保 models 目录存在
    local_path = os.path.join(MODELS_DIR, local_filename)
    logging.info(f"开始下载 {local_filename} 从 {url} 到 {local_path}...")
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()  # 如果请求失败则抛出 HTTPError 异常
            with open(local_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logging.info(f"文件 {local_filename} 下载完成，保存在 {local_path}")
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"下载 {local_filename} 失败: {e}")
        if os.path.exists(local_path): # 如果下载失败但文件已创建，则删除不完整的文件
            os.remove(local_path)
        return False

def check_and_download_dependencies(include_english: bool = False):
    """
    检查所有依赖文件，如果不存在则下载到 models 目录
    
    Args:
        include_english: 是否包含英文模型依赖（用于中英混合TTS）
    """
    ensure_dir_exists(MODELS_DIR) # 确保检查前 models 目录已创建
    all_files_present = True
    
    # 下载中文模型依赖
    for filename, url in CHINESE_DEPENDENCIES.items():
        local_path = os.path.join(MODELS_DIR, filename)
        if not os.path.exists(local_path):
            logging.warning(f"依赖文件 {filename} 在 {MODELS_DIR} 中不存在，尝试下载...")
            if not download_file(url, filename):
                all_files_present = False
                logging.error(f"未能下载必需的依赖文件: {filename}。程序可能无法正常运行。")
        else:
            logging.info(f"依赖文件 {filename} 已存在于 {local_path}")
    
    # 下载英文模型依赖（如果需要）
    if include_english:
        for filename, url in ENGLISH_DEPENDENCIES.items():
            local_path = os.path.join(MODELS_DIR, filename)
            if not os.path.exists(local_path):
                logging.warning(f"英文模型依赖文件 {filename} 在 {MODELS_DIR} 中不存在，尝试下载...")
                if not download_file(url, filename):
                    # 英文模型下载失败不影响整体，只记录警告
                    logging.warning(f"未能下载英文模型依赖文件: {filename}。中英混合TTS功能可能不可用。")
            else:
                logging.info(f"英文模型依赖文件 {filename} 已存在于 {local_path}")
    
    if all_files_present:
        logging.info("所有依赖文件均已在 models 目录就绪。")
    else:
        logging.warning("部分依赖文件下载失败或未找到。请检查日志获取详细信息。")
    return all_files_present


def check_and_download_english_dependencies():
    """单独检查和下载英文模型依赖"""
    ensure_dir_exists(MODELS_DIR)
    all_files_present = True
    
    for filename, url in ENGLISH_DEPENDENCIES.items():
        local_path = os.path.join(MODELS_DIR, filename)
        if not os.path.exists(local_path):
            logging.warning(f"英文模型依赖文件 {filename} 在 {MODELS_DIR} 中不存在，尝试下载...")
            if not download_file(url, filename):
                all_files_present = False
                logging.error(f"未能下载英文模型依赖文件: {filename}")
        else:
            logging.info(f"英文模型依赖文件 {filename} 已存在于 {local_path}")
    
    return all_files_present

if __name__ == "__main__":
    check_and_download_dependencies() 