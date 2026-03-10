import httpx


class LLMService:
    """Service for interacting with the LLM backend."""

    def __init__(self, base_url: str, timeout_seconds: int):
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.client = httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release network resources."""
        await self.client.aclose()

    async def create_chat_completion(self, request_body: dict) -> dict:
        """Sends a chat completion request to the LLM backend."""
        try:
            response = await self.client.post(
                f'{self.base_url}/v1/chat/completions',
                json=request_body,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError('LLM request timed out') from exc
        except httpx.HTTPStatusError:
            raise
        except httpx.RequestError as exc:
            raise ConnectionError('Failed to reach LLM backend') from exc
