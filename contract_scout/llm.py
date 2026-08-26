"""OpenAI-совместимый чат. Реквизиты сторон вырезаются до отправки."""

from __future__ import annotations

import logging

from contract_scout.config import Settings
from contract_scout.redact import redact_requisites

logger = logging.getLogger("contract_scout.llm")


class ChatLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if settings.openai_api_key:
            from openai import OpenAI

            self._client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    def complete(
        self,
        prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 3500,
        redact_output: bool = True,
        system: str | None = None,
    ) -> str:
        if not self.settings.llm_enabled or self._client is None:
            raise RuntimeError("Нет ключа LLM — облачный разбор недоступен.")
        payload = prompt
        redacted_n = 0
        if getattr(self.settings, "redact_requisites", True):
            payload, redacted_n = redact_requisites(prompt)
        messages = []
        if system:
            sys_text = system
            if getattr(self.settings, "redact_requisites", True):
                sys_text, n = redact_requisites(system)
                redacted_n += n
            messages.append({"role": "system", "content": sys_text})
        messages.append({"role": "user", "content": payload})
        resp = self._client.chat.completions.create(
            model=self.settings.chat_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        if redact_output and getattr(self.settings, "redact_requisites", True):
            text, extra = redact_requisites(text)
            redacted_n += extra
        logger.info("llm chars_in=%s chars_out=%s redacted=%s", len(payload), len(text), redacted_n)
        return text
