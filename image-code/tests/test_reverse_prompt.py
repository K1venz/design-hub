import asyncio
from collections.abc import AsyncIterator
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from design_hub.application.image_prompts.reverse_prompt import (
    ReversePromptRequest,
    ReversePromptResult,
    ReversePromptService,
)
from design_hub.application.listing.upload_service import UploadService
from design_hub.domain.enums import Role
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import AuthUser
from design_hub.infrastructure.providers.mock_text import MockTextLLMProvider
from design_hub.interface.api.app import register_error_handlers
from design_hub.interface.api.deps import get_current_user
from design_hub.interface.api.routes import image_prompts
from design_hub.ports.image_store import ImageStore, StoredImage
from design_hub.ports.listing_query import (
    GeneratedImageSource,
    ListingHistoryQuery,
)
from design_hub.ports.text_llm import (
    ChatMessage,
    LLMChunk,
    TextLLMError,
    TextLLMPort,
    ToolCall,
    ToolCallChunk,
    ToolSpec,
)
from design_hub.ports.upload_store import UploadStore, upload_ns

_RESULT = {
    "summary": "暖色咖啡店中的商品摄影",
    "subject": "银白色无线耳机充电盒",
    "scene": "现代咖啡店木质桌面",
    "composition": "商品居中偏下，背景虚化",
    "camera": "接近平视的中近景产品摄影",
    "lighting": "左前方柔和自然光",
    "colors": ["暖棕色", "银白色", "米色"],
    "style": "写实商业产品摄影",
    "visible_text": ["SOUND"],
    "constraints": ["保持商品比例和金属材质"],
    "uncertainties": ["无法仅根据图片确定真实焦段"],
    "prompt_zh": "银白色无线耳机充电盒置于咖啡店木桌上",
    "prompt_en": "A silver wireless earbud charging case on a cafe table",
}


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (32, 24), "white").save(output, format="PNG")
    return output.getvalue()


class _LLM(TextLLMPort):
    is_live = True

    def __init__(self, arguments: dict | None = _RESULT) -> None:
        self.arguments = arguments
        self.messages: list[ChatMessage] = []
        self.tools: list[ToolSpec] = []

    async def complete(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
    ) -> AsyncIterator[LLMChunk]:
        self.messages = messages
        self.tools = tools
        if self.arguments is not None:
            yield ToolCallChunk(
                (
                    ToolCall(
                        id="reverse-1",
                        name="return_reverse_prompt",
                        arguments=self.arguments,
                    ),
                )
            )


class _Uploads(UploadStore):
    def __init__(self, images: dict[str, tuple[bytes, str]]) -> None:
        self.images = images
        self.loaded: list[str] = []

    async def save(self, data: bytes, *, content_type: str, user_id: str) -> str:
        raise AssertionError("save is not used")

    async def load(self, upload_id: str) -> tuple[bytes, str]:
        self.loaded.append(upload_id)
        try:
            return self.images[upload_id]
        except KeyError:
            raise NotFoundError(f"上传图不存在：{upload_id}") from None


class _Images(ImageStore):
    def __init__(self, images: dict[str, bytes] | None = None) -> None:
        self.images = images or {}
        self.loaded: list[str] = []

    async def save(self, data: bytes, *, suffix: str = ".png") -> StoredImage:
        raise AssertionError("save is not used")

    async def load(self, image_key: str) -> bytes:
        self.loaded.append(image_key)
        try:
            return self.images[image_key]
        except KeyError:
            raise NotFoundError(f"出图不存在：{image_key}") from None


class _Query(ListingHistoryQuery):
    def __init__(self, source: GeneratedImageSource | None = None) -> None:
        self.source = source

    async def list_jobs(
        self,
        *,
        user_id: str,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> list[object]:
        return []

    async def get_job(self, *, job_id: str, user_id: str) -> object | None:
        return None

    async def resolve_generated_image_source(
        self,
        *,
        source_image_key: str,
        user_id: str,
    ) -> GeneratedImageSource | None:
        return self.source


def _service(
    *,
    llm: _LLM,
    uploads: _Uploads | None = None,
    images: _Images | None = None,
    query: _Query | None = None,
) -> ReversePromptService:
    return ReversePromptService(
        text_llm=llm,
        uploads=UploadService(uploads or _Uploads({})),
        images=images or _Images(),
        query=query or _Query(),
    )


def test_reverse_prompt_request_is_strict_and_reuses_image_source_contract() -> None:
    request = ReversePromptRequest.model_validate(
        {
            "source": {
                "kind": "generated",
                "image_key": "generated.png",
            }
        }
    )

    assert request.source.kind == "generated"
    with pytest.raises(ValidationError):
        ReversePromptRequest.model_validate(
            {
                "source": {
                    "kind": "generated",
                    "image_key": "generated.png",
                    "upload_id": "upload.png",
                }
            }
        )
    with pytest.raises(ValidationError):
        ReversePromptRequest.model_validate(
            {
                "source": {
                    "kind": "upload",
                    "upload_id": "upload.png",
                },
                "model": "another-model",
            }
        )


def test_reverse_uploaded_image_uses_real_bytes_and_strict_result_schema() -> None:
    async def run() -> None:
        upload_id = f"{upload_ns('user-1')}/product.png"
        uploads = _Uploads({upload_id: (_png(), "image/png")})
        llm = _LLM()
        service = _service(llm=llm, uploads=uploads)

        result = await service.reverse(
            user_id="user-1",
            request=ReversePromptRequest.model_validate(
                {
                    "source": {
                        "kind": "upload",
                        "upload_id": upload_id,
                    }
                }
            ),
        )

        assert result == ReversePromptResult.model_validate(_RESULT)
        assert uploads.loaded == [upload_id]
        assert len(llm.tools) == 1
        assert llm.tools[0].name == "return_reverse_prompt"
        assert llm.tools[0].required is True
        assert llm.messages[-1].images[0].data == _png()
        assert llm.messages[-1].images[0].media_type == "image/png"

    asyncio.run(run())


def test_reverse_uploaded_image_works_with_mock_text_provider() -> None:
    async def run() -> None:
        upload_id = f"{upload_ns('user-1')}/product.png"
        service = ReversePromptService(
            text_llm=MockTextLLMProvider(),
            uploads=UploadService(
                _Uploads({upload_id: (_png(), "image/png")})
            ),
            images=_Images(),
            query=_Query(),
        )

        result = await service.reverse(
            user_id="user-1",
            request=ReversePromptRequest.model_validate(
                {
                    "source": {
                        "kind": "upload",
                        "upload_id": upload_id,
                    }
                }
            ),
        )

        assert result.summary == "一张待分析的商品图片"
        assert result.prompt_zh
        assert result.prompt_en

    asyncio.run(run())


def test_reverse_prompt_route_returns_structured_result() -> None:
    upload_id = f"{upload_ns('user-1')}/product.png"
    service = _service(
        llm=_LLM(),
        uploads=_Uploads({upload_id: (_png(), "image/png")}),
    )
    app = FastAPI()
    app.include_router(image_prompts.router)
    register_error_handlers(app)
    app.state.reverse_prompt_service = service

    async def user() -> AuthUser:
        return AuthUser(user_id="user-1", name="User", role=Role.DESIGNER)

    app.dependency_overrides[get_current_user] = user
    client = TestClient(app)

    response = client.post(
        "/image-prompts/reverse",
        json={
            "source": {
                "kind": "upload",
                "upload_id": upload_id,
            }
        },
    )

    assert response.status_code == 200
    assert response.json() == _RESULT


def test_reverse_prompt_route_reports_invalid_model_output() -> None:
    upload_id = f"{upload_ns('user-1')}/product.png"
    service = _service(
        llm=_LLM(None),
        uploads=_Uploads({upload_id: (_png(), "image/png")}),
    )
    app = FastAPI()
    app.include_router(image_prompts.router)
    register_error_handlers(app)
    app.state.reverse_prompt_service = service

    async def user() -> AuthUser:
        return AuthUser(user_id="user-1", name="User", role=Role.DESIGNER)

    app.dependency_overrides[get_current_user] = user
    response = TestClient(app).post(
        "/image-prompts/reverse",
        json={
            "source": {
                "kind": "upload",
                "upload_id": upload_id,
            }
        },
    )

    assert response.status_code == 502
    assert response.json()["error"] == "text_llm_failed"


def test_reverse_generated_image_checks_owner_before_loading_bytes() -> None:
    async def run() -> None:
        source = GeneratedImageSource(
            parent_job_id="parent-1",
            parent_ratio="1:1",
            parent_modifiers={},
            root_product_upload_keys=("root/product.png",),
        )
        images = _Images({"generated.png": _png()})
        service = _service(
            llm=_LLM(),
            images=images,
            query=_Query(source),
        )

        result = await service.reverse(
            user_id="user-1",
            request=ReversePromptRequest.model_validate(
                {
                    "source": {
                        "kind": "generated",
                        "image_key": "generated.png",
                    }
                }
            ),
        )

        assert result.subject == _RESULT["subject"]
        assert images.loaded == ["generated.png"]

        unauthorized_images = _Images({"foreign.png": _png()})
        unauthorized = _service(
            llm=_LLM(),
            images=unauthorized_images,
            query=_Query(None),
        )
        with pytest.raises(NotFoundError):
            await unauthorized.reverse(
                user_id="user-1",
                request=ReversePromptRequest.model_validate(
                    {
                        "source": {
                            "kind": "generated",
                            "image_key": "foreign.png",
                        }
                    }
                ),
            )
        assert unauthorized_images.loaded == []

    asyncio.run(run())


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        {**_RESULT, "prompt_en": ""},
        {**_RESULT, "unexpected": "field"},
    ],
)
def test_reverse_prompt_rejects_missing_or_invalid_tool_output(
    arguments: dict | None,
) -> None:
    async def run() -> None:
        upload_id = f"{upload_ns('user-1')}/product.png"
        service = _service(
            llm=_LLM(arguments),
            uploads=_Uploads({upload_id: (_png(), "image/png")}),
        )

        with pytest.raises(TextLLMError):
            await service.reverse(
                user_id="user-1",
                request=ReversePromptRequest.model_validate(
                    {
                        "source": {
                            "kind": "upload",
                            "upload_id": upload_id,
                        }
                    }
                ),
            )

    asyncio.run(run())
