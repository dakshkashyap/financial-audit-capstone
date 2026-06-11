"""
Multi-backend model abstraction for AuditBench.

Supports:
  - OpenAI API (GPT-3.5, GPT-4, etc.)
  - Google Gemini (via OpenAI-compatible endpoint)
  - Ollama (local models via OpenAI-compatible API)
  - Qwen (via Dashscope API)
  - Kimi (Moonshot AI API)
  - Hugging Face Transformers (local inference)

Usage:
  client = get_model_client("ollama/llama3")
  response = client.generate(messages, temperature=1.0)
"""

import os
import json
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


class ModelBackend(ABC):
    """Abstract base class for all model backends."""
    
    def __init__(self, model_name: str, **kwargs):
        self.model_name = model_name
        self.kwargs = kwargs
    
    @abstractmethod
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        """
        Generate a response from the model.
        
        Args:
            messages: List of {"role": "system/user/assistant", "content": "..."}
            temperature: Sampling temperature
            
        Returns:
            {"content": str, "model": str}
        """
        pass


class OpenAIBackend(ModelBackend):
    """OpenAI API backend (GPT-3.5, GPT-4, etc.)"""
    
    def __init__(self, model_name: str, **kwargs):
        super().__init__(model_name, **kwargs)
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not set")
        self.client = openai.OpenAI(api_key=api_key)
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        return {
            "content": resp.choices[0].message.content,
            "model": resp.model,
        }


class GeminiBackend(ModelBackend):
    """Google Gemini via OpenAI-compatible endpoint."""
    
    def __init__(self, model_name: str, **kwargs):
        super().__init__(model_name, **kwargs)
        import openai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set")
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        return {
            "content": resp.choices[0].message.content,
            "model": resp.model,
        }


class OllamaBackend(ModelBackend):
    """Ollama local models via OpenAI-compatible API."""
    
    def __init__(self, model_name: str, base_url: str = "http://localhost:11434/v1", **kwargs):
        super().__init__(model_name, **kwargs)
        import openai
        self.client = openai.OpenAI(
            api_key="ollama",  # Ollama doesn't need real API key
            base_url=base_url,
        )
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        return {
            "content": resp.choices[0].message.content,
            "model": self.model_name,
        }


class QwenBackend(ModelBackend):
    """Qwen models via Alibaba Dashscope API."""
    
    def __init__(self, model_name: str, **kwargs):
        super().__init__(model_name, **kwargs)
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            raise EnvironmentError("DASHSCOPE_API_KEY not set for Qwen models")
        self.api_key = api_key
        # Dashscope uses OpenAI-compatible format
        import openai
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        return {
            "content": resp.choices[0].message.content,
            "model": self.model_name,
        }


class KimiBackend(ModelBackend):
    """Kimi (Moonshot AI) API backend."""
    
    def __init__(self, model_name: str, **kwargs):
        super().__init__(model_name, **kwargs)
        api_key = os.environ.get("MOONSHOT_API_KEY")
        if not api_key:
            raise EnvironmentError("MOONSHOT_API_KEY not set for Kimi models")
        import openai
        self.client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1",
        )
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        resp = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
        )
        return {
            "content": resp.choices[0].message.content,
            "model": resp.model,
        }


class HuggingFaceBackend(ModelBackend):
    """Local inference via Hugging Face Transformers."""
    
    def __init__(self, model_name: str, device: str = "auto", **kwargs):
        super().__init__(model_name, **kwargs)
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import torch
        except ImportError:
            raise ImportError("transformers and torch required for HuggingFace backend")
        
        print(f"Loading {model_name} from Hugging Face... (this may take a while)")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            device_map=device,
            trust_remote_code=True,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        )
        self.model.eval()
    
    def generate(self, messages: List[Dict[str, str]], temperature: float = 1.0) -> Dict[str, Any]:
        # Format messages into a prompt (model-specific formatting may be needed)
        prompt = self._format_messages(messages)
        
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=temperature,
            do_sample=temperature > 0,
            top_p=0.95,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        
        response = self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        
        return {
            "content": response,
            "model": self.model_name,
        }
    
    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        """Format messages into a single prompt string."""
        # Try to use the tokenizer's chat template if available
        if hasattr(self.tokenizer, "apply_chat_template"):
            return self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        
        # Fallback: simple concatenation
        prompt_parts = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt_parts.append(f"System: {content}\n")
            elif role == "user":
                prompt_parts.append(f"User: {content}\n")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}\n")
        prompt_parts.append("Assistant:")
        return "\n".join(prompt_parts)


# ── Model Registry ──────────────────────────────────────────────────────────

MODEL_CONFIGS = {
    # OpenAI models
    "gpt-3.5-turbo": {"backend": OpenAIBackend, "model_name": "gpt-3.5-turbo"},
    "gpt-3.5-turbo-0125": {"backend": OpenAIBackend, "model_name": "gpt-3.5-turbo-0125"},
    "gpt-4": {"backend": OpenAIBackend, "model_name": "gpt-4"},
    "gpt-4-0613": {"backend": OpenAIBackend, "model_name": "gpt-4-0613"},
    "gpt-4-turbo": {"backend": OpenAIBackend, "model_name": "gpt-4-turbo"},
    "gpt-4o": {"backend": OpenAIBackend, "model_name": "gpt-4o"},
    
    # Gemini models
    "gemini-2.0-flash": {"backend": GeminiBackend, "model_name": "gemini-2.0-flash"},
    "gemini-1.5-pro": {"backend": GeminiBackend, "model_name": "gemini-1.5-pro"},
    "gemini-1.5-flash": {"backend": GeminiBackend, "model_name": "gemini-1.5-flash"},
    
    # Ollama models (common ones, user can add more)
    "ollama/llama3": {"backend": OllamaBackend, "model_name": "llama3"},
    "ollama/llama3.1": {"backend": OllamaBackend, "model_name": "llama3.1"},
    "ollama/llama3.2": {"backend": OllamaBackend, "model_name": "llama3.2"},
    "ollama/mistral": {"backend": OllamaBackend, "model_name": "mistral"},
    "ollama/mixtral": {"backend": OllamaBackend, "model_name": "mixtral"},
    "ollama/qwen2.5": {"backend": OllamaBackend, "model_name": "qwen2.5"},
    "ollama/phi3": {"backend": OllamaBackend, "model_name": "phi3"},
    
    # Qwen models via Dashscope
    "qwen/qwen-turbo": {"backend": QwenBackend, "model_name": "qwen-turbo"},
    "qwen/qwen-plus": {"backend": QwenBackend, "model_name": "qwen-plus"},
    "qwen/qwen-max": {"backend": QwenBackend, "model_name": "qwen-max"},
    "qwen/qwen-long": {"backend": QwenBackend, "model_name": "qwen-long"},
    
    # Kimi models
    "kimi/moonshot-v1-8k": {"backend": KimiBackend, "model_name": "moonshot-v1-8k"},
    "kimi/moonshot-v1-32k": {"backend": KimiBackend, "model_name": "moonshot-v1-32k"},
    "kimi/moonshot-v1-128k": {"backend": KimiBackend, "model_name": "moonshot-v1-128k"},
    
    # Hugging Face models (local inference)
    "hf/Qwen/Qwen2.5-7B-Instruct": {"backend": HuggingFaceBackend, "model_name": "Qwen/Qwen2.5-7B-Instruct"},
    "hf/Qwen/Qwen2.5-14B-Instruct": {"backend": HuggingFaceBackend, "model_name": "Qwen/Qwen2.5-14B-Instruct"},
    "hf/meta-llama/Llama-3.1-8B-Instruct": {"backend": HuggingFaceBackend, "model_name": "meta-llama/Llama-3.1-8B-Instruct"},
    "hf/mistralai/Mistral-7B-Instruct-v0.3": {"backend": HuggingFaceBackend, "model_name": "mistralai/Mistral-7B-Instruct-v0.3"},
}


def get_model_client(model_identifier: str, **kwargs) -> ModelBackend:
    """
    Factory function to get the appropriate model backend.
    
    Args:
        model_identifier: Model name (e.g., "gpt-4", "ollama/llama3", "qwen/qwen-turbo")
        **kwargs: Additional arguments passed to the backend
        
    Returns:
        ModelBackend instance
        
    Examples:
        >>> client = get_model_client("gpt-4")
        >>> client = get_model_client("ollama/llama3")
        >>> client = get_model_client("kimi/moonshot-v1-8k")
    """
    if model_identifier in MODEL_CONFIGS:
        config = MODEL_CONFIGS[model_identifier]
        backend_class = config["backend"]
        model_name = config["model_name"]
        return backend_class(model_name, **kwargs)
    else:
        raise ValueError(
            f"Unknown model: {model_identifier}\n"
            f"Available models:\n" + 
            "\n".join(f"  - {k}" for k in sorted(MODEL_CONFIGS.keys()))
        )


def list_available_models() -> Dict[str, List[str]]:
    """List all available models grouped by backend."""
    models_by_backend = {}
    for model_id, config in MODEL_CONFIGS.items():
        backend_name = config["backend"].__name__.replace("Backend", "")
        if backend_name not in models_by_backend:
            models_by_backend[backend_name] = []
        models_by_backend[backend_name].append(model_id)
    return models_by_backend


if __name__ == "__main__":
    print("Available models:")
    for backend, models in list_available_models().items():
        print(f"\n{backend}:")
        for model in models:
            print(f"  - {model}")
