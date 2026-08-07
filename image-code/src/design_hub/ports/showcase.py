from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ShowcaseCandidate:
    image_id: int
    image_key: str
    image_type: str | None
    status: str
    moderation_status: str
    prompt: str
    category: str | None
    ratio: str
    modifiers: dict[str, object]
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


@dataclass(frozen=True)
class PublicShowcaseRecipe:
    category: str
    ratio: str
    plan: dict[str, int]
    modifiers: dict[str, str]


@dataclass(frozen=True)
class PublicShowcaseItem:
    image_id: int
    preview_key: str
    image_type: str | None
    prompt: str
    download_allowed: bool
    width: int
    height: int
    recipe: PublicShowcaseRecipe | None


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

    @abstractmethod
    async def list_public(self) -> tuple[PublicShowcaseItem, ...]: ...

    @abstractmethod
    async def get_download_key(self, image_id: int) -> str | None: ...
