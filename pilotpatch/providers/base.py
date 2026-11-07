from typing import Protocol


class ProviderError(RuntimeError):
    pass


class AuthenticationRequired(ProviderError):
    pass


class CopilotProvider(Protocol):
    async def send(self, prompt: str) -> str: ...

    async def close(self) -> None: ...
