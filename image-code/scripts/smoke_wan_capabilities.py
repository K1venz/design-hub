import argparse
import asyncio
import json
import time
from pathlib import Path
from uuid import uuid4

from design_hub.application.diagnostics.wan_capability_smoke import (
    SMOKE_RATIOS,
    SmokeResult,
    build_evidence,
    image_dimensions,
)
from design_hub.composition import build_image_store, build_secret_cipher
from design_hub.config.settings import Settings
from design_hub.domain.admin import ModelOperation
from design_hub.domain.image_capabilities import image_model_capabilities
from design_hub.domain.tasking import RenderTier
from design_hub.infrastructure.db.model_call_repo import (
    SqlAlchemyModelCallRecorder,
)
from design_hub.infrastructure.db.model_config_repo import (
    SqlAlchemyModelConfigRepository,
)
from design_hub.infrastructure.db.session import (
    create_engine,
    create_session_factory,
)
from design_hub.infrastructure.providers.live_resolution import (
    LiveImageExecutorResolver,
)
from design_hub.ports.model_calls import ModelCallContext
from design_hub.ports.provider_execution import ProviderRequest, SubmittedTask

MODEL_ID = "wan2.7-image-pro"
PROMPT = (
    "Create a premium abstract product-design composition with one matte ceramic "
    "object, a warm ivory background, soft studio lighting, subtle geometric "
    "accents, no text, no logo, and balanced detail across the full canvas."
)


async def run_smoke(
    *,
    settings: Settings,
    output_dir: Path,
    evidence_path: Path,
) -> dict[str, object]:
    engine = create_engine(settings.db_url)
    sessions = create_session_factory(engine)
    image_store = build_image_store(settings)
    resolver = LiveImageExecutorResolver(
        repository=SqlAlchemyModelConfigRepository(sessions),
        cipher=build_secret_cipher(settings),
        recorder=SqlAlchemyModelCallRecorder(sessions),
        image_store=image_store,
        settings=settings,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[SmokeResult] = []
    active_ratio: str | None = None
    try:
        capabilities = image_model_capabilities(MODEL_ID)
        executor = await resolver.resolve(MODEL_ID, RenderTier.STANDARD)
        for ratio in SMOKE_RATIOS:
            active_ratio = ratio
            output = capabilities.output_for(RenderTier.STANDARD, ratio)
            operation_id = f"wan-smoke-{ratio.replace(':', 'x')}-{uuid4().hex[:8]}"
            request = ProviderRequest(
                context=ModelCallContext(
                    user_id="wan-capability-smoke",
                    operation=ModelOperation.IMAGE_GENERATION,
                ),
                prompt=PROMPT,
                reference_images=(),
                output=output,
                seed=0,
                quality=None,
            )
            started_at = time.monotonic()
            submitted = await executor.submit(request, operation_id=operation_id)
            if not isinstance(submitted, SubmittedTask):
                raise RuntimeError("Wan smoke expected an asynchronous task")
            image = await executor.resume(submitted.provider_task_id, request)
            data = await image_store.load(image.image_key)
            actual_size = image_dimensions(data)
            suffix = _safe_suffix(image.image_key)
            artifact_path = output_dir / f"wan-{ratio.replace(':', 'x')}{suffix}"
            artifact_path.write_bytes(data)
            results.append(
                SmokeResult(
                    ratio=ratio,
                    requested_size=output.size,
                    task_id=submitted.provider_task_id,
                    status="passed",
                    actual_size=actual_size,
                    latency_ms=max(
                        int((time.monotonic() - started_at) * 1000),
                        0,
                    ),
                    artifact_path=str(artifact_path),
                )
            )
        evidence = build_evidence(results)
        _write_evidence(evidence_path, evidence)
        return evidence
    except Exception as exc:
        _write_evidence(
            evidence_path,
            {
                "model": MODEL_ID,
                "render_tier": RenderTier.STANDARD.value,
                "passed": False,
                "results": [result.__dict__ for result in results],
                "failure": {
                    "ratio": active_ratio,
                    "error_type": type(exc).__name__,
                },
            },
        )
        raise
    finally:
        await engine.dispose()


def _safe_suffix(image_key: str) -> str:
    suffix = Path(image_key).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Wan smoke result has an unsupported suffix")
    return suffix


def _write_evidence(path: Path, evidence: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("exports/wan-capability-smoke"),
    )
    parser.add_argument(
        "--evidence-path",
        type=Path,
        default=Path(
            "docs/superpowers/evidence/2026-08-06-wan-extreme-ratios.json"
        ),
    )
    args = parser.parse_args()
    evidence = asyncio.run(
        run_smoke(
            settings=Settings(),
            output_dir=args.output_dir,
            evidence_path=args.evidence_path,
        )
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
