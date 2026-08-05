"""Run paid Nano Banana generation and edit smoke checks with process-only keys."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

from design_hub.domain.admin import ModelOperation
from design_hub.domain.image_capabilities import image_model_capabilities
from design_hub.domain.models import ReferenceImage
from design_hub.domain.nano_banana import (
    NANO_BANANA_2_MODEL_ID,
    NANO_BANANA_UPSTREAM_MODEL,
)
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.providers.api_key_pool import ApiKeyPool
from design_hub.infrastructure.providers.gemini_native import (
    GeminiNativeImageProvider,
)
from design_hub.infrastructure.storage.local import LocalImageStore
from design_hub.ports.model_calls import ModelCallContext, ModelUsage


class _SafeRecorder:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def start(
        self,
        *,
        context: ModelCallContext,
        provider: str,
        model: str,
        attempt_no: int,
    ) -> str:
        call_id = f"smoke-{len(self.events) + 1}"
        self.events.append(
            {
                "call_id": call_id,
                "operation": context.operation.value,
                "provider": provider,
                "model": model,
                "attempt_no": attempt_no,
            }
        )
        return call_id

    async def succeed(
        self,
        call_id: str,
        *,
        usage: ModelUsage,
        provider_request_id: str | None,
        platform_cost: Decimal | None,
        diagnostic_code: str | None = None,
    ) -> None:
        self.events.append(
            {
                "call_id": call_id,
                "status": "succeeded",
                "usage": asdict(usage),
                "provider_request_id": provider_request_id,
                "platform_cost": str(platform_cost),
                "diagnostic_code": diagnostic_code,
            }
        )

    async def fail(self, call_id: str, *, code: str, detail: str) -> None:
        self.events.append(
            {"call_id": call_id, "status": "failed", "code": code, "detail": detail}
        )

    async def uncertain(self, call_id: str, *, detail: str) -> None:
        self.events.append(
            {"call_id": call_id, "status": "uncertain", "detail": detail}
        )

    async def interrupt(self, call_id: str) -> None:
        self.events.append({"call_id": call_id, "status": "interrupted"})


def _required_keys() -> tuple[str, ...]:
    raw = os.environ.get("NANO_BANANA_API_KEYS", "")
    keys = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not keys:
        raise ValueError("NANO_BANANA_API_KEYS is required")
    return keys


async def _run() -> dict[str, object]:
    output_root = os.environ.get("NANO_SMOKE_OUTPUT_DIR")
    temp: tempfile.TemporaryDirectory[str] | None = None
    if output_root:
        output_dir = Path(output_root)
    else:
        temp = tempfile.TemporaryDirectory()
        output_dir = Path(temp.name)
    store = LocalImageStore(str(output_dir))
    recorder = _SafeRecorder()
    provider = GeminiNativeImageProvider(
        name=NANO_BANANA_2_MODEL_ID,
        unit_cost=Decimal("0"),
        base_url=os.environ.get("NANO_BANANA_BASE_URL", "https://api.yhlxj.ai"),
        key_pool=ApiKeyPool(_required_keys()),
        model=NANO_BANANA_UPSTREAM_MODEL,
        image_store=store,
        recorder=recorder,
        max_retries=1,
    )
    output = image_model_capabilities(NANO_BANANA_2_MODEL_ID).output_for(
        RenderTier.STANDARD, "4:5"
    )
    generated = await provider.generate(
        context=ModelCallContext(
            user_id="nano-smoke",
            operation=ModelOperation.IMAGE_GENERATION,
        ),
        prompt=(
            "Create a clean studio product poster for a cobalt blue insulated bottle, "
            "soft daylight, pale gray background, no text."
        ),
        negative_prompt="watermark, distorted bottle",
        reference_images=[],
        output=output,
        n=1,
    )
    generated_bytes = await store.load(generated[0].image_key)
    edited = await provider.generate(
        context=ModelCallContext(
            user_id="nano-smoke",
            operation=ModelOperation.IMAGE_EDIT,
        ),
        prompt="Keep the bottle unchanged and replace the background with warm beige.",
        negative_prompt="watermark, extra bottle",
        reference_images=[ReferenceImage(data=generated_bytes)],
        output=output,
        n=1,
    )
    serialized_events = json.dumps(recorder.events, ensure_ascii=False)
    if "sk-" in serialized_events or "inlineData" in serialized_events:
        raise RuntimeError("unsafe model-call metadata")
    result = {
        "status": "passed",
        "model": NANO_BANANA_2_MODEL_ID,
        "output": {"tier": output.render_tier.value, "ratio": output.ratio},
        "generated_image_key": generated[0].image_key,
        "edited_image_key": edited[0].image_key,
        "provider_attempts": sum("attempt_no" in event for event in recorder.events),
        "safe_metadata": True,
        "output_dir": str(output_dir),
    }
    if temp is not None:
        temp.cleanup()
        result["output_dir"] = "temporary-cleaned"
    return result


def main() -> None:
    print(json.dumps(asyncio.run(_run()), ensure_ascii=False))


if __name__ == "__main__":
    main()
