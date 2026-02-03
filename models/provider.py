# models/provider.py - Universal LLM interface
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List
import os
import aiohttp
import json

class BaseModelProvider(ABC):
    """Abstract base for any LLM - local or API"""
    
    @abstractmethod
    async def generate(self, messages: List[Dict], tools: List[Dict] = None) -> str:
        pass
    
    @abstractmethod
    async def stream_generate(self, messages: List[Dict], tools: List[Dict] = None) -> AsyncGenerator[str, None]:
        pass

class LocalHuggingFaceProvider(BaseModelProvider):
    """Local models via Transformers (Qwen, Llama, Mistral)"""
    
    def __init__(self, model_id: str = "Qwen/Qwen2.5-7B-Instruct"):
        from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
        import torch
        
        self.model_id = model_id
        self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True
        )
        self.pipeline = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            max_new_tokens=2048,
            temperature=0.7
        )
    
    async def generate(self, messages, tools=None):
        prompt = self._format_messages(messages)
        result = self.pipeline(prompt)[0]['generated_text']
        return result[len(prompt):].strip()
    
    async def stream_generate(self, messages, tools=None):
        """Stream tokens for real-time UI updates"""
        prompt = self._format_messages(messages)
        # Implementation depends on model's streaming capability
        yield await self.generate(messages, tools)  # Simplified
    
    def _format_messages(self, messages: List[Dict]) -> str:
        """Convert chat format to model-specific format"""
        if "qwen" in self.model_id.lower():
            return self._format_qwen(messages)
        elif "llama" in self.model_id.lower():
            return self._format_llama(messages)
        else:
            return self._format_generic(messages)
    
    def _format_qwen(self, messages):
        """Qwen chat template"""
        prompt = ""
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                prompt += f"<|im_start|>system\n{content}<|im_end|>\n"
            elif role == "user":
                prompt += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == "assistant":
                prompt += f"<|im_start|>assistant\n{content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        return prompt

class OllamaProvider(BaseModelProvider):
    """Local models via Ollama (easier management)"""
    
    def __init__(self, model: str = "qwen2.5:7b", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host
    
    async def generate(self, messages, tools=None):
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7}
            }
            async with session.post(f"{self.host}/api/chat", json=payload) as resp:
                data = await resp.json()
                return data["message"]["content"]
    
    async def stream_generate(self, messages, tools=None):
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": True
            }
            async with session.post(f"{self.host}/api/chat", json=payload) as resp:
                async for line in resp.content:
                    if line:
                        data = json.loads(line)
                        if "message" in data:
                            yield data["message"]["content"]

class OpenAICompatibleProvider(BaseModelProvider):
    """For Groq, OpenAI, Together AI, etc."""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    async def generate(self, messages, tools=None):
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "temperature": 0.7
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/v1/chat/completions",
                headers=headers,
                json=payload
            ) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

class ModelRouter:
    """Auto-selects best model for task"""
    
    PROVIDERS = {
        "local_qwen": lambda: LocalHuggingFaceProvider("Qwen/Qwen2.5-7B-Instruct"),
        "local_llama": lambda: LocalHuggingFaceProvider("meta-llama/Llama-3.3-70B-Instruct"),
        "local_mistral": lambda: LocalHuggingFaceProvider("mistralai/Mistral-Small-3.1-24B-Instruct-2503"),
        "ollama": lambda: OllamaProvider(os.getenv("OLLAMA_MODEL", "qwen2.5:7b")),
        "groq": lambda: OpenAICompatibleProvider(
            os.getenv("GROQ_API_KEY"),
            "https://api.groq.com/openai",
            "mixtral-8x7b-32768"
        ),
        "openai": lambda: OpenAICompatibleProvider(
            os.getenv("OPENAI_API_KEY"),
            "https://api.openai.com",
            "gpt-4o-mini"
        )
    }
    
    def __init__(self):
        self.provider = self._init_provider()
    
    def _init_provider(self):
        provider_type = os.getenv("MODEL_PROVIDER", "ollama")
        if provider_type in self.PROVIDERS:
            return self.PROVIDERS[provider_type]()
        raise ValueError(f"Unknown provider: {provider_type}")
    
    async def generate(self, messages, tools=None):
        return await self.provider.generate(messages, tools)
    
    async def route_by_complexity(self, user_input: str, messages: List[Dict]):
        """Smart routing: fast local model for simple queries, API for complex"""
        simple_keywords = ["hello", "hi", "thanks", "bye", "what is"]
        is_simple = any(kw in user_input.lower() for kw in simple_keywords)
        
        if is_simple and os.getenv("FAST_MODEL"):
            # Use small local model (3B) for latency
            fast_provider = LocalHuggingFaceProvider("Qwen/Qwen2.5-3B-Instruct")
            return await fast_provider.generate(messages)
        
        # Use main provider
        return await self.provider.generate(messages)