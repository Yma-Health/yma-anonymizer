import time
from typing import Any

from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletion
from structlog import get_logger
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import LLMConfig
from app.services.prompts import ANONYMIZE_PROMPT

logger = get_logger(__name__)

RETRY_ATTEMPTS_COUNT = 3


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "Retrying OpenAI call",
        attempt=retry_state.attempt_number,
        wait_seconds=(retry_state.next_action.sleep if retry_state.next_action is not None else None),
        last_error=(str(exc) if exc else None),
        error_type=(type(exc).__name__ if exc else None),
        endpoint="/responses",
    )


def _log_response(response: ChatCompletion, start_time: float) -> None:
    elapsed_s = round(time.monotonic() - start_time, 2)
    log = logger.bind(elapsed_s=elapsed_s, model=response.model)
    usage = response.usage
    if usage is None:
        log.warning("No usage data in response; skipping cost calculation")
        return

    log.info(
        "Chat completion completed",
        tokens=dict(
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        ),
    )


openai_retry = retry(
    reraise=True,
    stop=stop_after_attempt(RETRY_ATTEMPTS_COUNT),
    wait=wait_exponential(multiplier=2, max=120, exp_base=2),
    retry=retry_if_exception_type(
        (
            RateLimitError,
            APIError,
            APIConnectionError,
            APITimeoutError,
            TimeoutError,
        ),
    ),
    before_sleep=_log_retry,
)


class LLMService:
    def __init__(self, client: AsyncOpenAI, config: LLMConfig):
        self.client = client
        self.config = config

    async def chat_completion(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        model: str | None = None,
        **kwargs: Any,
    ) -> str | None:
        start_time = time.monotonic()
        if model is None:
            model = self.config.model

        log = logger.bind(model=model, prompt_len=len(prompt), kwargs=kwargs)

        messages = [{"role": "user", "content": prompt}]
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        log.info("Starting structured generation")
        try:
            response: ChatCompletion = await self.client.chat.completions.create(
                model=model,
                messages=messages,  # type: ignore
                temperature=temperature,
                extra_headers={"mode": "instruct", "instruction_template": "Alpaca"},
                **kwargs,
            )
        except (
            RateLimitError,
            APIError,
            APIConnectionError,
            APITimeoutError,
            TimeoutError,
        ) as e:
            log.error("Chat completion attempt failed", error=str(e), exc_info=True)
            raise

        except Exception as e:
            log.error("Chat completion failed", error=str(e), exc_info=True)
            raise

        _log_response(response, start_time)
        return response.choices[0].message.content

    async def anonymize(self, text: str, *, temperature: float = 0.7) -> str | None:
        return await self.chat_completion(text, system_prompt=ANONYMIZE_PROMPT, temperature=temperature)
