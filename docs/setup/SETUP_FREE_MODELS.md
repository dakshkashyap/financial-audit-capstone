# Setup Guide: Free Open-Source Models

This guide shows you how to run AuditBench with **100% free open-source models** (no API keys needed).

## Option 1: Ollama (Recommended - Easiest)

**Ollama** runs models locally on your machine with a simple interface.

### Step 1: Install Ollama

```bash
# macOS
brew install ollama

# Or download from: https://ollama.ai
```

### Step 2: Start Ollama

```bash
ollama serve
```

Keep this running in a separate terminal.

### Step 3: Download Models

```bash
# Llama 3.1 (8B) - Good balance of speed and quality
ollama pull llama3.1

# Qwen 2.5 (7B) - Excellent for reasoning tasks
ollama pull qwen2.5

# Other options:
ollama pull llama3.2    # Latest Llama
ollama pull mistral     # Fast and capable
ollama pull phi3        # Small but powerful
```

### Step 4: Run AuditBench

```bash
# Install dependencies
pip install -r requirements.txt

# Test with dry run (free, instant)
python main.py --dry-run --n 8

# Run with Llama 3.1
python main.py --model ollama/llama3.1 --split single_error --n 10

# Run with Qwen 2.5
python main.py --model ollama/qwen2.5 --split single_error --n 10

# Compare multiple models
python main.py --model ollama/llama3.1,ollama/qwen2.5,ollama/mistral --split single_error --n 50

# Full dataset (will take time!)
python main.py --model ollama/llama3.1 --split single_error --n 1484
```

---

## Option 2: Hugging Face Transformers (Local Inference)

**Pros**: More control, many models available  
**Cons**: Requires more GPU memory, slower setup

### Step 1: Install Dependencies

```bash
pip install torch transformers accelerate
```

### Step 2: Run with Hugging Face Models

```bash
# Qwen 2.5 7B Instruct
python main.py --model hf/Qwen/Qwen2.5-7B-Instruct --split single_error --n 10

# Llama 3.1 8B (requires authentication with Meta)
python main.py --model hf/meta-llama/Llama-3.1-8B-Instruct --split single_error --n 10

# Mistral 7B
python main.py --model hf/mistralai/Mistral-7B-Instruct-v0.3 --split single_error --n 10
```

**Note**: First run will download the model (5-15GB). This is cached for future use.

---

## Option 3: Qwen via API (Free Tier)

Qwen offers a free API tier through Alibaba Cloud.

### Step 1: Get API Key

1. Sign up at: https://dashscope.aliyun.com/
2. Get your API key from the dashboard

### Step 2: Set Environment Variable

```bash
export DASHSCOPE_API_KEY=sk-your-key-here
```

### Step 3: Run

```bash
python main.py --model qwen/qwen-turbo --split single_error --n 10
```

---

## Recommended Workflow for FREE Models

### Quick Test (5 minutes)
```bash
# 1. Install Ollama and pull llama3.1
ollama serve
ollama pull llama3.1

# 2. Test with small sample
python main.py --model ollama/llama3.1 --split single_error --n 10
```

### Full Comparison (1-2 hours)
```bash
# Compare multiple models on moderate sample
python main.py --model ollama/llama3.1,ollama/qwen2.5,ollama/mistral \
  --split single_error --n 100
```

### Complete Benchmark (several hours)
```bash
# Run full dataset with best model
python main.py --model ollama/llama3.1 --split single_error --n 1484
python main.py --model ollama/llama3.1 --split multi_error --n 372
python main.py --model ollama/llama3.1 --split correct --n 371
```

---

## Available Free Models

Run this to see all available models:
```bash
python main.py --model list
```

### Ollama Models (Local, Free)
- `ollama/llama3.1` - Meta's Llama 3.1 8B
- `ollama/llama3.2` - Latest Llama
- `ollama/qwen2.5` - Alibaba's Qwen 2.5 7B
- `ollama/mistral` - Mistral 7B
- `ollama/phi3` - Microsoft's Phi-3

### Hugging Face Models (Local, Free)
- `hf/Qwen/Qwen2.5-7B-Instruct`
- `hf/Qwen/Qwen2.5-14B-Instruct` (needs more RAM)
- `hf/meta-llama/Llama-3.1-8B-Instruct`
- `hf/mistralai/Mistral-7B-Instruct-v0.3`

---

## System Requirements

### For Ollama (Recommended)
- **RAM**: 8GB minimum, 16GB recommended
- **Disk**: 10GB free space per model
- **OS**: macOS, Linux, or Windows

### For Hugging Face
- **RAM**: 16GB minimum
- **GPU**: Optional but recommended (CUDA/MPS)
- **Disk**: 15GB free space per model

---

## Troubleshooting

### Ollama not connecting
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Restart Ollama
pkill ollama
ollama serve
```

### Model too slow
```bash
# Use smaller/faster model
python main.py --model ollama/phi3 --split single_error --n 10

# Reduce sample size
python main.py --model ollama/llama3.1 --split single_error --n 50
```

### Out of memory
```bash
# Use Ollama instead of Hugging Face
# Or use smaller model like phi3
```

---

## Cost Comparison

| Method | Cost | Speed | Quality |
|--------|------|-------|---------|
| **Ollama (Llama 3.1)** | $0 | Fast | High |
| **Ollama (Qwen 2.5)** | $0 | Fast | High |
| **Hugging Face (Local)** | $0 | Medium | High |
| **Qwen API (Free Tier)** | $0* | Fast | High |
| OpenAI GPT-4 | ~$30-50 | Fastest | Highest |
| Google Gemini | ~$10-20 | Fast | High |

*Free tier has daily limits

---

## Next Steps

1. **Test first**: `python main.py --dry-run --n 8`
2. **Small run**: `python main.py --model ollama/llama3.1 --split single_error --n 10`
3. **Compare models**: Try different models and compare results
4. **Full benchmark**: Run complete dataset when ready

**Questions?** Check the main README.md or model_backends.py for more details.
