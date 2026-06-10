"""Простой потокобезопасный для asyncio лимитер запросов по пользователям."""
import time
from collections import defaultdict, deque


class RateLimiter:
    """Скользящее окно: не более `max_calls` обращений за `window` секунд."""

    def __init__(self, max_calls: int, window: float):
        self.max_calls = max_calls
        self.window = window
        self._calls: dict[int, deque] = defaultdict(deque)

    def allow(self, user_id: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._calls[user_id]
        # выкидываем устаревшие отметки
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.max_calls:
            return False
        q.append(now)
        return True

    def retry_after(self, user_id: int, now: float | None = None) -> float:
        """Сколько секунд ждать до следующего разрешённого запроса."""
        now = time.monotonic() if now is None else now
        q = self._calls[user_id]
        if not q:
            return 0.0
        return max(0.0, self.window - (now - q[0]))
