# setup.sh - One-command setup
#!/bin/bash

echo "🚀 OpenAgent Setup - Superior OpenClaw Alternative"

# Check dependencies
command -v docker >/dev/null 2>&1 || { echo "❌ Docker required"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3.11+ required"; exit 1; }

# Create directories
mkdir -p workspace data/memory skills

# Download default model if using local
read -p "Download Qwen2.5-7B model? (requires 15GB disk) [y/N]: " download_model
if [[ $download_model =~ ^[Yy]$ ]]; then
    echo "📥 Pulling model with Ollama..."
    docker run -v ollama:/root/.ollama -p 11434:11434 ollama/ollama pull qwen2.5:7b
fi

# Configure environment
if [ ! -f .env ]; then
    cat > .env << EOF
TELEGRAM_TOKEN=your_telegram_bot_token_here
DEFAULT_MODEL=Qwen/Qwen2.5-7B-Instruct
SANDBOX_MODE=docker
EOF
    echo "⚠️  Edit .env with your API tokens"
fi

# Build and run
docker-compose up --build -d

echo ""
echo "✅ OpenAgent Gateway running at ws://localhost:18789"
echo "📱 Connect Telegram: Set TELEGRAM_TOKEN in .env and restart"
echo "🌐 Web UI: http://localhost:18789"
echo ""
echo "Security features active:"
echo "  • Docker sandboxing for shell commands"
echo "  • Memory limits (512MB per tool)"
echo "  • Network isolation for untrusted code"
echo "  • Path traversal protection"