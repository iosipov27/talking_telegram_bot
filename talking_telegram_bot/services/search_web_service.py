from talking_telegram_bot.clients.tavily_client import TavilyClient, TavilyClientError
from talking_telegram_bot.models.search import SearchWebResponse


class SearchWebServiceError(RuntimeError):
    """Raised when web search can not be completed safely."""


class SearchWebService:
    def __init__(self, tavily_client: TavilyClient, max_results: int = 5) -> None:
        self._tavily_client = tavily_client
        self._max_results = max_results

    async def search_web(self, raw_query: str) -> SearchWebResponse:
        query = raw_query.strip()
        if not query:
            raise SearchWebServiceError("Search query is empty.")
        try:
            return await self._tavily_client.search(query, self._max_results)
        except TavilyClientError as exc:
            raise SearchWebServiceError("Web search is unavailable.") from exc

