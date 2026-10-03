#!/bin/bash
# Quick start script for running AuditBench with FREE open-source models

set -e

echo "================================================"
echo "AuditBench - Free Open-Source Model Quick Start"
echo "================================================"
echo ""

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama not found!"
    echo ""
    echo "Please install Ollama first:"
    echo "  macOS: brew install ollama"
    echo "  Or visit: https://ollama.ai"
    echo ""
    exit 1
fi

echo "✅ Ollama is installed"
echo ""

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags &> /dev/null; then
    echo "⚠️  Ollama is not running. Starting Ollama..."
    echo ""
    echo "Opening Ollama in the background..."
    ollama serve &> /dev/null &
    sleep 3
    echo "✅ Ollama started"
else
    echo "✅ Ollama is running"
fi
echo ""

# Check if llama3.1 is available
echo "Checking for models..."
if ollama list | grep -q "llama3.1"; then
    echo "✅ llama3.1 is available"
else
    echo "📥 Downloading llama3.1 (this may take a few minutes)..."
    ollama pull llama3.1
    echo "✅ llama3.1 downloaded"
fi
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Run a quick test
echo "================================================"
echo "Running quick test (dry run)..."
echo "================================================"
python main.py --dry-run --n 8
echo ""

echo "================================================"
echo "Running with Llama 3.1 (10 samples)..."
echo "================================================"
python main.py --model ollama/llama3.1 --split single_error --n 10
echo ""

echo "================================================"
echo "✅ Quick start complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. View results in: results/"
echo "  2. Run more models: python main.py --model list"
echo "  3. Full benchmark: python main.py --model ollama/llama3.1 --split single_error --n 1484"
echo "  4. Read the guide: SETUP_FREE_MODELS.md"
echo ""
