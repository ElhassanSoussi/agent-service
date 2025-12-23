# Ollama Integration for Agent Service

This document explains how to use a self-hosted Ollama LLM instead of OpenAI or Anthropic.

## Overview

The agent-service now supports Ollama as an LLM provider, allowing you to run a completely self-hosted setup with no external API calls.

## Prerequisites

1. A server with sufficient RAM (8GB+ recommended for llama3.1:8b)
2. Ollama installed and running
3. A model pulled (e.g., llama3.1)

## Installation Commands

### Install Ollama

```bash
# Download and install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Verify installation
ollama --version
```

### Set Up Ollama as a System Service

Ollama typically runs as a systemd service automatically after installation. Check status:

```bash
# Check if Ollama service is running
sudo systemctl status ollama

# Start if not running
sudo systemctl start ollama

# Enable to start on boot
sudo systemctl enable ollama

# View logs
sudo journalctl -u ollama -f
```

### Pull a Model

```bash
# Pull llama3.1 (recommended, ~4.7GB download)
ollama pull llama3.1

# Or pull a smaller model (faster, less accurate)
ollama pull llama3.2:3b

# Or pull a larger model (slower, more accurate)
ollama pull llama3.1:70b

# List installed models
ollama list
```

### Verify Ollama is Working

```bash
# Test with curl
curl http://127.0.0.1:11434/api/tags

# Test generation
curl -X POST http://127.0.0.1:11434/api/generate \
  -d '{"model": "llama3.1", "prompt": "Hello!", "stream": false}'

# Interactive test
ollama run llama3.1 "Hello! What can you do?"
```

## Configuration

### Environment Variables

Add these to your `/etc/agent-service.env` or `.env` file:

```bash
# Enable LLM planner mode (optional, default is "rules")
AGENT_PLANNER_MODE=llm

# Set provider to Ollama
LLM_PROVIDER=ollama

# Ollama base URL (default: http://127.0.0.1:11434)
LLM_BASE_URL=http://127.0.0.1:11434

# Model to use (default: llama3.1)
LLM_MODEL=llama3.1

# Timeout in seconds (increase for slower hardware)
LLM_TIMEOUT_S=60

# No API key needed for Ollama!
# LLM_API_KEY= (not required)
```

### Minimal Configuration (Ollama defaults)

If Ollama is running locally with defaults, you only need:

```bash
LLM_PROVIDER=ollama
```

## Endpoints

### Health Check (Public)

```bash
# Check LLM health
curl http://localhost:8000/llm/health
```

Response:
```json
{
  "status": "ok",
  "provider": "ollama",
  "model": "llama3.1",
  "base_url": "http://127.0.0.1:11434",
  "message": "Ollama is running. Models available: llama3.1",
  "planner_mode": "llm"
}
```

### Direct Generation (Requires Auth)

```bash
# Generate text directly
curl -X POST http://localhost:8000/llm/generate \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

Response:
```json
{
  "status": "ok",
  "response": "The capital of France is Paris.",
  "error": null,
  "provider": "ollama",
  "model": "llama3.1"
}
```

## Using with Chat UI

1. Navigate to `http://YOUR_SERVER:8000/ui/chat`
2. Enter your AGENT_API_KEY (same as before)
3. Start chatting!

The chat will use Ollama for generating responses when `LLM_PROVIDER=ollama` is set.

## Troubleshooting

### Ollama Not Responding

```bash
# Check if Ollama is running
sudo systemctl status ollama

# Check if port is listening
ss -tlnp | grep 11434

# Restart Ollama
sudo systemctl restart ollama
```

### Model Not Found

```bash
# List available models
ollama list

# Pull missing model
ollama pull llama3.1
```

### Slow Responses

1. Use a smaller model: `LLM_MODEL=llama3.2:3b`
2. Increase timeout: `LLM_TIMEOUT_S=120`
3. Check system resources: `htop`

### Connection Refused

Ensure Ollama is binding to the correct address:

```bash
# Check Ollama config
cat /etc/systemd/system/ollama.service

# If needed, add OLLAMA_HOST to bind to all interfaces:
# Environment="OLLAMA_HOST=0.0.0.0"
```

### Memory Issues

```bash
# Check memory usage
free -h

# For low-memory systems, use smaller models
ollama pull llama3.2:1b
```

## Model Recommendations

| Model | Size | RAM Required | Speed | Quality |
|-------|------|--------------|-------|---------|
| llama3.2:1b | ~1GB | 4GB | Very Fast | Basic |
| llama3.2:3b | ~2GB | 6GB | Fast | Good |
| llama3.1:8b | ~4.7GB | 10GB | Medium | Very Good |
| llama3.1:70b | ~40GB | 64GB+ | Slow | Excellent |

## Security Notes

1. **Ollama should only listen on localhost** (127.0.0.1) by default
2. Do NOT expose Ollama to the internet
3. Agent-service handles authentication; Ollama doesn't need it
4. Keep the `AGENT_API_KEY` secret

## Comparison: Ollama vs Cloud Providers

| Feature | Ollama | OpenAI | Anthropic |
|---------|--------|--------|-----------|
| Cost | Free | Pay per token | Pay per token |
| Privacy | Full (local) | Data sent to API | Data sent to API |
| Speed | Depends on hardware | Fast | Fast |
| API Key | Not needed | Required | Required |
| Internet | Not needed | Required | Required |
| Quality | Model dependent | GPT-4 class | Claude class |
