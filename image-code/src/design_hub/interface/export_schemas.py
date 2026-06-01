"""导出归档 HTTP schema（边界翻译，WP-E）。"""

from pydantic import BaseModel, Field

from design_hub.application.export.export_service import ExportResult
from design_hub.ports.exporter import ExportFormat


class ResizeSpec(BaseModel):
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class ExportRequest(BaseModel):
    image_ids: list[int] = Field(min_length=1)
    formats: list[ExportFormat] = Field(min_length=1)
    resize: ResizeSpec | None = None
    zip: bool = False


class ExportFileOut(BaseModel):
    filename: str
    url: str


class ExportResponse(BaseModel):
    package_url: str | None
    files: list[ExportFileOut]

    @classmethod
    def of(cls, r: ExportResult) -> "ExportResponse":
        return cls(
            package_url=r.package_url,
            files=[ExportFileOut(filename=f.filename, url=f.url) for f in r.files],
        )


class ResizeRequest(BaseModel):
    w: int = Field(gt=0)
    h: int = Field(gt=0)
    format: ExportFormat = ExportFormat.PNG


class ResizeResponse(BaseModel):
    url: str
