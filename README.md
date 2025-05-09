# kokoro-onnx-fastapi

基于[kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx)开发的轻量级语音合成API服务，采用FastAPI框架构建。本项目提供简便易用的本地或服务器语音合成解决方案，支持中文及其他语言（如英文）的高质量语音生成。

## 项目特点

- 🚀 高性能FastAPI接口，响应迅速
- 🐳 完整支持Docker容器化部署
- 🌏 中文和其他语言模型分离部署（位于src/chinese和src/other目录）
- 📦 首次启动自动下载并管理依赖资源
- 💾 支持音频文件缓存，提高重复请求响应速度
- 🔄 支持语音生成速度调节
- 🧩 丰富多样的声音模型选择

**中文与其他语言模型分离说明：**  
中文语音模型[Kokoro-82M-v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)与其他语言模型[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)是两个独立的项目，拥有不同的模型结构和语音特性。本项目通过目录隔离实现两套模型的独立部署与按需使用，避免不必要的资源占用。

## 系统要求

- Python 3.12或更高版本
- [uv包管理工具](https://docs.astral.sh/uv/getting-started/installation)（推荐使用）
- 约1GB磁盘空间用于存储模型文件
- Docker与docker-compose（如需容器化部署）

## 快速开始

### 本地运行

#### 中文语音服务

```bash
# 克隆代码仓库
git clone https://github.com/kamjin3086/kokoro-onnx-fastapi.git

# 进入中文模型目录
cd kokoro-onnx-fastapi/src/chinese

# 创建Python虚拟环境
uv venv -p 3.12

# 激活虚拟环境
## Windows系统:
.venv\Scripts\activate
## Linux/MacOS系统:
source .venv/bin/activate

# 安装项目依赖
uv pip install -r requirements.txt

# 启动服务
python main.py
```

服务将在`http://localhost:8210`端口运行，首次启动时会自动下载所需模型文件。

#### 其他语言语音服务

```bash
# 克隆代码仓库（如已克隆可跳过）
git clone https://github.com/kamjin3086/kokoro-onnx-fastapi.git

# 进入其他语言模型目录
cd kokoro-onnx-fastapi/src/other

# 创建Python虚拟环境
uv venv -p 3.12

# 激活虚拟环境
## Linux/MacOS系统:
source .venv/bin/activate
## Windows系统:
.venv\Scripts\activate

# 安装项目依赖
uv pip install -r requirements.txt

# 启动服务
python main.py
```

服务将在`http://localhost:8211`端口运行。

### Docker容器部署

#### 中文语音服务

```bash
# 克隆代码仓库（如已克隆可跳过）
git clone https://github.com/kamjin3086/kokoro-onnx-fastapi.git

# 进入中文模型目录
cd kokoro-onnx-fastapi/src/chinese

# 构建并启动Docker容器
docker-compose up -d --build
```

容器化服务将在`http://localhost:8210`端口运行。

#### 其他语言语音服务

```bash
# 克隆代码仓库（如已克隆可跳过）
git clone https://github.com/kamjin3086/kokoro-onnx-fastapi.git

# 进入其他语言模型目录
cd kokoro-onnx-fastapi/src/other

# 构建并启动Docker容器
docker-compose up -d --build
```

容器化服务将在`http://localhost:8211`端口运行。

## API使用指南

API接口文档访问地址：`http://localhost:8210/docs`（中文服务）或`http://localhost:8211/docs`（其他语言服务）

### 中文语音合成API

**接口**：`POST /generate-speech/`

**请求参数**：
- `text`：要转换的中文文本内容
- `voice`：选择的声音模型（如"zf_001"）
- `filename`（可选）：生成音频的文件名（不含路径和扩展名）
- `speed`（可选）：语音速度调节，默认为1.0

**请求示例**：

```bash
curl -X POST "http://localhost:8210/generate-speech/" \
     -H "Content-Type: application/json" \
     -d '{"text":"你好，世界！", "voice":"zf_001", "filename":"hello_world", "speed": 1.0}' \
     --output hello_world.wav
```

### 其他语言语音合成API

**接口**：`POST /generate-speech/`

**请求参数**：
- `text`：要转换的文本内容（如英文）
- `voice`：选择的声音模型（如"en-us-kathleen-low"或"af_heart"）
- `filename`（可选）：生成音频的文件名（不含路径和扩展名）
- `speed`（可选）：语音速度调节，默认为1.0

**请求示例**：

```bash
curl -X POST "http://localhost:8211/generate-speech/" \
     -H "Content-Type: application/json" \
     -d '{"text":"Hello world, this is a test.", "voice":"en-us-kathleen-low", "filename":"hello_test", "speed": 1.0}' \
     --output hello_test.wav
```

## 配置与自定义

- 模型文件自动下载并保存至各自服务目录下的`models/`文件夹
- 生成的音频文件存储在各自服务目录下的`generated_audio/`文件夹
- 可通过编辑`main.py`配置文件调整服务参数

## 项目结构

```
.
├── src/
│   ├── chinese/             # 中文语音合成服务
│   │   ├── main.py          # 主应用程序
│   │   ├── download_deps.py # 依赖下载工具
│   │   ├── cache.py         # 音频缓存工具
│   │   ├── Dockerfile       # Docker配置
│   │   ├── docker-compose.yaml  # Docker Compose配置
│   │   ├── requirements.txt # 项目依赖列表
│   │   ├── models/          # 模型文件目录
│   │   └── generated_audio/ # 生成音频存储目录
│   │
│   └── other/               # 其他语言语音合成服务
│       ├── main.py          # 主应用程序
│       ├── download_deps.py # 依赖下载工具
│       ├── Dockerfile       # Docker配置
│       ├── docker-compose.yaml  # Docker Compose配置
│       ├── requirements.txt # 项目依赖列表
│       ├── models/          # 模型文件目录
│       └── generated_audio/ # 生成音频存储目录
```

## 声音模型说明

### 中文声音模型
使用`v1.1-zh`版本模型，提供多种中文女声和男声选择。

### 其他语言声音模型
使用`v1.0`版本模型，支持多种语言和声音类型。

详细的声音模型列表请参考[Kokoro项目文档](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)。

## 许可证

本项目采用MIT许可证，基于[原kokoro-onnx项目](https://github.com/thewh1teagle/kokoro-onnx)开发，请同时遵循原项目的许可要求。 