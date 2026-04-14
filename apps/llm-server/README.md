# LLM Server

Local inference server for running Large Language Models using llama.cpp. Provides
an OpenAI-compatible API for chat completions.

## Overview

This directory contains instructions for setting up a local LLM server that serves
models with an OpenAI-compatible HTTP API. The assistant backend (`apps/assistant-backend`)
communicates with this server via the `/v1/chat/completions` endpoint.

There are two ways to run the LLM server:

1. **Docker Compose** (recommended) — the `docker-compose.yml` in the repository root
   includes a `llama-cpp-python` service. Place your GGUF model at
   `~/models/meta-llama-3.1-8b-instruct-q4_k_m.gguf` and run `docker compose up`.
2. **Manually on the host** — follow the Quick Start below to install and run the server
   directly. This is useful for GPU-accelerated inference or when running only part of the
   stack in Docker.

**Key Features:**

- OpenAI-compatible API
- Runs quantized models efficiently on consumer hardware
- Supports llama.cpp GGUF format models
- Configurable chat formats (llama-3, chatml, etc.)

## Prerequisites

- **Python 3.8+** with pip
- **8GB+ RAM** (16GB+ recommended for 8B parameter models)
- **Disk Space**: ~5GB per model
- **(Optional)** CUDA-capable GPU for faster inference
- **(Optional)** Hugging Face account for downloading models

## Quick Start

### 1. Install UV Package Manager

UV is a fast Python package installer and resolver:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal or run:

```bash
source $HOME/.cargo/env
```

### 2. Download a Model

**Option A: Using uvx (recommended)**

```bash
uvx hf download \
  joshnader/Meta-Llama-3.1-8B-Instruct-Q4_K_M-GGUF \
  meta-llama-3.1-8b-instruct-q4_k_m.gguf \
  --local-dir ./models
```

```bash
uvx hf download \
  bartowski/Qwen2.5-7B-Instruct-GGUF \
  Qwen2.5-7B-Instruct-Q4_K_M.gguf \
  --local-dir ~/models
```

```bash
uvx hf download \
  bartowski/Qwen2.5-7B-Instruct-GGUF \
  Qwen2.5-7B-Instruct-Q5_K_M.gguf \
  --local-dir ~/models
```

**Option B: Using huggingface-cli**

Use the hugging face UI.

**Popular Model Options:**

- `joshnader/Meta-Llama-3.1-8B-Instruct-Q4_K_M-GGUF` - Balanced performance
- `bartowski/Meta-Llama-3.1-8B-Instruct-GGUF` - Multiple quantization options
- `TheBloke/Mistral-7B-Instruct-v0.2-GGUF` - Efficient alternative

### 3. Install llama-cpp-python Server

```bash
pip install llama-cpp-python[server]
```

**For GPU acceleration (NVIDIA CUDA):**

```bash
CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python[server]
```

**For Metal acceleration (Apple Silicon):**

```bash
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python[server]
```

### 4. Run the Server

```bash
python -m llama_cpp.server \
  --model ./models/meta-llama-3.1-8b-instruct-q4_k_m.gguf \
  --chat_format llama-3 \
  --host 0.0.0.0 \
  --port 8000
```

The server will start and be available at `http://localhost:8000`

**Important:** The assistant-backend expects the LLM server at the URL specified in
`LLM_BASE_URL` environment variable (defaults to `http://host.docker.internal:8000`).

## Configuration Options

### Common Parameters

- `--model <path>` - Path to the GGUF model file **(required)**
- `--chat_format <format>` - Chat template format (e.g., `llama-3`, `chatml`, `mistral-instruct`)
- `--host <host>` - Host to bind to (default: `localhost`, use `0.0.0.0` for remote access)
- `--port <port>` - Port to listen on (default: `8000`)
- `--n_ctx <size>` - Context window size (default: `2048`, increase for longer conversations)
- `--n_gpu_layers <layers>` - Number of layers to offload to GPU (default: `0`, use `-1` for all)
- `--n_threads <threads>` - Number of CPU threads to use

### Example: High-Performance Configuration

```bash
python -m llama_cpp.server \
  --model ./models/meta-llama-3.1-8b-instruct-q4_k_m.gguf \
  --chat_format llama-3 \
  --host 0.0.0.0 \
  --port 8000 \
  --n_ctx 4096 \
  --n_gpu_layers -1 \
  --n_threads 8
```

## Remote Access via SSH

If running the LLM server on a remote machine, use SSH port forwarding to access it locally:

```bash
ssh -L 8000:localhost:8000 user@remote-host
```

Then configure your backend to use `http://localhost:8000` as the `LLM_BASE_URL`.

## Testing the Server

### Health Check

```bash
curl http://localhost:8000/health
```

### Test Chat Completion

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama-3.1-8b",
    "messages": [
      {"role": "user", "content": "Hello, who are you?"}
    ],
    "temperature": 0.7,
    "max_tokens": 100
  }'
```

Expected response:

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1234567890,
  "model": "llama-3.1-8b",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm an AI assistant..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 15,
    "total_tokens": 25
  }
}
```

## Integration with Assistant Backend

Update the backend configuration in `apps/assistant-backend/.env` (or the root `.env` for Docker Compose):

```env
LLM_BASE_URL=http://localhost:8000
LLM_MODEL=llama-3.1-8b-instruct
LLM_TIMEOUT_SECONDS=120
```

When running via Docker Compose the backend connects to the `llama-cpp-python` service
automatically; the `LLM_BASE_URL` is set to `http://llama-cpp-python:8000` inside the
container network. For local development outside Docker, point `LLM_BASE_URL` at the
host address where the server is running.

The backend will automatically connect to the LLM server and use it for chat completions
via the `/v1/chat/completions` endpoint.

## Troubleshooting

### Server won't start

**Issue**: `ImportError: cannot import name 'Llama'`

- **Solution**: Reinstall llama-cpp-python: `pip uninstall llama-cpp-python && pip install llama-cpp-python[server]`

**Issue**: Model file not found

- **Solution**: Verify the path to your GGUF file is correct and the file exists

### Slow inference

**Issue**: Inference is very slow

- **Solution**:
  - Enable GPU acceleration if you have a compatible GPU
  - Reduce `--n_ctx` to decrease context window size
  - Use a smaller quantized model (e.g., Q4_K_M instead of Q8_0)
  - Increase `--n_threads` to match your CPU cores

### Out of memory errors

**Issue**: Server crashes with OOM errors

- **Solution**:
  - Use a more aggressively quantized model (Q2_K, Q3_K_M)
  - Reduce `--n_ctx` to decrease memory usage
  - Close other applications to free up RAM
  - If using GPU, reduce `--n_gpu_layers`

### Connection refused from backend

**Issue**: Backend can't reach LLM server

- **Solution**:
  - Verify the server is running: `curl http://localhost:8000/health`
  - Check `LLM_BASE_URL` in backend `.env` matches the server host/port
  - Ensure firewall allows connections on the specified port
  - For remote servers, verify SSH port forwarding is active

## Model Recommendations

| Model | Size | RAM Required | Best For |
|-------|------|--------------|----------|
| Meta-Llama-3.1-8B-Instruct (Q4_K_M) | ~5GB | 8GB+ | General purpose, good quality/speed balance |
| Meta-Llama-3.1-8B-Instruct (Q8_0) | ~8GB | 12GB+ | Higher quality, slower inference |
| Mistral-7B-Instruct (Q4_K_M) | ~4GB | 6GB+ | Efficient, faster inference |
| Phi-3-mini (Q4_K_M) | ~2.5GB | 4GB+ | Low resource environments |

## Resources

- [llama.cpp Documentation](https://github.com/ggerganov/llama.cpp)
- [llama-cpp-python Server](https://github.com/abetlen/llama-cpp-python)
- [Hugging Face GGUF Models](https://huggingface.co/models?library=gguf)
- [OpenAI API Documentation](https://platform.openai.com/docs/api-reference/chat)

## License

This setup uses third-party tools and models. Refer to their respective licenses:

- llama.cpp: MIT License
- Model licenses vary by provider

