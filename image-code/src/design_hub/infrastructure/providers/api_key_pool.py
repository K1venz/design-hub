"""逻辑请求级 API Key 轮换池。"""


class ApiKeyPool:
    """在单一 asyncio event loop 中为每个逻辑请求分配一次轮换起点。"""

    def __init__(self, keys: tuple[str, ...]) -> None:
        normalized = tuple(key.strip() for key in keys if key.strip())
        if not normalized:
            raise ValueError("at least one API key is required")
        self._keys = normalized
        self._next_index = 0

    def reserve(self) -> int:
        index = self._next_index
        self._next_index = (self._next_index + 1) % len(self._keys)
        return index

    def key_for(self, start_index: int, attempt: int) -> str:
        return self._keys[(start_index + attempt) % len(self._keys)]

    def __repr__(self) -> str:
        return f"ApiKeyPool(size={len(self._keys)})"
