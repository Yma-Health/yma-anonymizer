from lagom import Container, Singleton
from openai import AsyncOpenAI

from app.config import LLMConfig, SimplexConfig
from app.services import LLMService, SimplexService

container = Container()

container[LLMConfig] = LLMConfig()
container[SimplexConfig] = SimplexConfig()


# Services
container[AsyncOpenAI] = Singleton(
    lambda c: AsyncOpenAI(
        api_key=container[LLMConfig].api_key,
        timeout=container[LLMConfig].timeout_seconds,
        base_url=container[LLMConfig].base_url,
    ),
)
container[LLMService] = Singleton(LLMService)
container[SimplexService] = Singleton(SimplexService)
