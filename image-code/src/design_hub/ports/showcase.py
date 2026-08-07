from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ShowcaseCandidate:
    image_id: int
    image_key: str
    status: str
    moderation_status: str
    prompt: str
    is_public: bool
    download_allowed: bool
    preview_key: str | None
    preview_width: int | None
    preview_height: int | None


@dataclass(frozen=True)
class ShowcasePublication:
    image_id: int
    is_public: bool
    download_allowed: bool
    preview_width: int | None
    preview_height: int | None
    showcased_at: datetime | None
    showcased_by: int | None


class ShowcaseRepository(ABC):
    @abstractmethod
    async def get_candidate(self, image_id: int) -> ShowcaseCandidate | None: ...

    @abstractmethod
    async def set_publication(
        self,
        *,
        actor_id: int,
        image_id: int,
        is_public: bool,
        download_allowed: bool,
        preview_key: str | None,
        preview_width: int | None,
        preview_height: int | None,
    ) -> ShowcasePublication: ...
