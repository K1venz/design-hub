from datetime import datetime

from pydantic import BaseModel, Field

from design_hub.domain.enums import RevisionStatus
from design_hub.domain.models import RevisionItem, RevisionRecord


class RevisionOpenRequest(BaseModel):
    round_no: int | None = None
    deadline: datetime | None = None


class AddItemRequest(BaseModel):
    text: str = Field(min_length=1)
    related_image_id: int | None = None


class ToggleItemRequest(BaseModel):
    done: bool


class RevisionItemOut(BaseModel):
    seq: int
    text: str
    done: bool
    related_image_id: int | None

    @classmethod
    def of(cls, i: RevisionItem) -> "RevisionItemOut":
        return cls(seq=i.seq, text=i.text, done=i.done, related_image_id=i.related_image_id)


class RevisionOut(BaseModel):
    id: int
    project_id: int
    round_no: int
    status: RevisionStatus
    deadline: datetime | None
    items: list[RevisionItemOut]

    @classmethod
    def of(cls, r: RevisionRecord) -> "RevisionOut":
        return cls(
            id=r.id,
            project_id=r.project_id,
            round_no=r.round_no,
            status=r.status,
            deadline=r.deadline,
            items=[RevisionItemOut.of(i) for i in r.items],
        )
