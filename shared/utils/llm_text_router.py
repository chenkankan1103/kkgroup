from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional, Tuple

import aiohttp
from dotenv import load_dotenv

from utils.nvidia_ai import call_nvidia_ai

load_dotenv()
logger = logging.getLogger(__name__)

GEMINI_KEY = os.getenv("AI_API_KEY", "").strip()
GEMINI_KEY_BK = os.getenv("AI_API_KEY_BACKUP", "").strip()
GEMINI_MODEL = os.getenv("AI_API_MODEL", "gemini-2.0-flash").strip() or "gemini-2.0-flash"
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions").strip()
GROQ_MODEL = os.getenv("GROQ_API_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
TEXT_NVIDIA_TIMEOUT_SEC = int(os.getenv("AI_TEXT_NVIDIA_TIMEOUT", "12"))
TEXT_GEMINI_TIMEOUT_SEC = int(os.getenv("AI_TEXT_GEMINI_TIMEOUT", "8"))
TEXT_GROQ_TIMEOUT_SEC = int(os.getenv("AI_TEXT_GROQ_TIMEOUT", "8"))


def _messages_to_gemini(system_prompt: str, messages: List[Dict[str, str]]) -> Dict:
    contents = []
    for message in messages:
        role = message.get("role", "user")
        if role == "system":
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append({"role": gemini_role, "parts": [{"text": message.get("content", "")}]})

    return {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 900,
            "topP": 0.9,
        },
    }


async def _call_gemini(
    api_key: str,
    messages: List[Dict[str, str]],
    timeout_sec: int,
) -> Optional[str]:
    if not api_key:
        return None

    system_prompt = "你是一個有幫助的助手。"
    for message in messages:
        if message.get("role") == "system":
            system_prompt = message.get("content", system_prompt)
            break

    payload = _messages_to_gemini(system_prompt, messages)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
            async with session.post(url, json=payload, headers={"Content-Type": "application/json"}) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return None
                parts = candidates[0].get("content", {}).get("parts", [])
                texts = [part.get("text", "") for part in parts if part.get("text")]
                return "\n".join(texts).strip() or None
    except Exception as exc:
        logger.warning("Gemini text fallback failed: %s", exc)
        return None


async def _call_groq(
    messages: List[Dict[str, str]],
    max_tokens: int,
    timeout_sec: int,
) -> Optional[str]:
    if not GROQ_KEY:
        return None

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
            async with session.post(GROQ_URL, json=payload, headers=headers) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                choices = data.get("choices", [])
                if not choices:
                    return None
                return choices[0].get("message", {}).get("content", "").strip() or None
    except Exception as exc:
        logger.warning("Groq text fallback failed: %s", exc)
        return None


async def complete_text_with_fallback(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int = 900,
    nvidia_timeout: int = TEXT_NVIDIA_TIMEOUT_SEC,
    gemini_timeout: int = TEXT_GEMINI_TIMEOUT_SEC,
    groq_timeout: int = TEXT_GROQ_TIMEOUT_SEC,
) -> Tuple[Optional[str], str]:
    result = await call_nvidia_ai(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=nvidia_timeout,
    )
    if result:
        return result, "nvidia"

    result = await _call_gemini(GEMINI_KEY, messages, gemini_timeout)
    if result:
        return result, "gemini-main"

    result = await _call_gemini(GEMINI_KEY_BK, messages, gemini_timeout)
    if result:
        return result, "gemini-backup"

    result = await _call_groq(messages, max_tokens, groq_timeout)
    if result:
        return result, "groq"

    return None, "none"