"""
app/services/gemini_client.py — Thin async wrapper around google-generativeai.

Used by Stage 5 (Delta Extractor) in Phase 2 and all later pipeline stages.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import google.generativeai as genai

from app.config import settings

logger = logging.getLogger("notelm.gemini")

# Safety settings per maturity level (TDD Section 2.2)
SAFETY_SETTINGS_BY_LEVEL: dict[str, list[dict]] = {
    "general": [
        {"category": "HARM_CATEGORY_VIOLENCE",         "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",      "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ],
    "mature": [
        {"category": "HARM_CATEGORY_VIOLENCE",         "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",      "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ],
    "explicit": [
        {"category": "HARM_CATEGORY_VIOLENCE",         "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HATE_SPEECH",      "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ],
}


class GeminiClient:
    """
    Async Gemini client.  Initialised once at module level; both flash and pro
    models are lazily constructed on first use.

    Usage:
        result = await gemini.generate(prompt, model="flash", temperature=0.1,
                                        response_mime_type="application/json")
        data = json.loads(result.text)
    """

    def __init__(self) -> None:
        genai.configure(api_key=settings.gemini_api_key)
        self._flash: genai.GenerativeModel | None = None
        self._pro: genai.GenerativeModel | None = None

    @property
    def flash(self) -> genai.GenerativeModel:
        if self._flash is None:
            self._flash = genai.GenerativeModel("gemini-1.5-flash")
        return self._flash

    @property
    def pro(self) -> genai.GenerativeModel:
        if self._pro is None:
            self._pro = genai.GenerativeModel("gemini-1.5-pro")
        return self._pro

    async def generate(
        self,
        prompt: str,
        *,
        model: str = "flash",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        safety_settings: list[dict] | None = None,
        response_mime_type: str = "text/plain",
        tools: list | None = None,
        stream: bool = False,
    ) -> Any:
        """
        Fire an async generate_content call.
        Returns the raw GenerateContentResponse so callers can access .text,
        .candidates, .prompt_feedback, etc.
        """
        client = self.flash if model == "flash" else self.pro
        config = genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type=response_mime_type,
        )
        kwargs: dict[str, Any] = {"generation_config": config, "stream": stream}
        if safety_settings:
            kwargs["safety_settings"] = safety_settings
        if tools:
            kwargs["tools"] = tools

        logger.debug("Gemini %s call | temp=%.2f | mime=%s", model, temperature, response_mime_type)
        return await client.generate_content_async(prompt, **kwargs)

    async def generate_json(
        self,
        prompt: str,
        *,
        model: str = "flash",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        safety_settings: list[dict] | None = None,
    ) -> Any:
        """Convenience wrapper — returns parsed Python object from JSON mode."""
        response = await self.generate(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            safety_settings=safety_settings,
            response_mime_type="application/json",
        )
        return json.loads(response.text)


# Module-level singleton
gemini = GeminiClient()
