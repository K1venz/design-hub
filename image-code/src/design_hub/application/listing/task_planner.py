import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from uuid import uuid4

from design_hub.application.listing.background_replacement import (
    compose_background_replace_prompt,
)
from design_hub.application.listing.listing_service import build_listing_prompts
from design_hub.application.listing.prompt_composer import (
    CategoryCardRegistry,
    CloneModeRegistry,
    EditModeRegistry,
    ImageTypeRegistry,
    PromptModifierRegistry,
    compose_clone_prompt,
    compose_edit_prompt,
)
from design_hub.application.listing.requests import (
    BackgroundReplaceRequest,
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.sizing import generation_size
from design_hub.domain.models import ListingJobStart
from design_hub.domain.tasking import (
    GenerationItemSpec,
    OperationType,
    ReferenceSnapshot,
    ReferenceSource,
    RenderTier,
)
from design_hub.ports.generation_work import JobSubmission
from design_hub.ports.listing_query import GeneratedImageSource


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class ListingTaskPlanner:
    modifier_registry: PromptModifierRegistry
    card_registry: CategoryCardRegistry
    type_registry: ImageTypeRegistry
    clone_registry: CloneModeRegistry
    edit_registry: EditModeRegistry

    def plan_generate(
        self,
        *,
        user_id: str,
        request: ListingGenerateRequest,
        job_id: str,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model_id: str,
        unit_cost: Decimal,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> JobSubmission:
        overlay_texts = tuple(request.overlay_texts or ())
        prompts = build_listing_prompts(
            request.prompt,
            request.modifiers,
            self.modifier_registry,
            self.card_registry,
            self.type_registry,
            category=request.category,
            n=request.n,
            plan=request.plan,
            overlay_texts=overlay_texts,
        )
        size = generation_size(render_tier, request.ratio)
        references = tuple(
            ReferenceSnapshot(
                source=ReferenceSource.UPLOAD,
                object_key=key,
                role="product",
                order=index,
            )
            for index, key in enumerate(request.upload_ids)
        )
        items = tuple(
            self._item(
                sequence=index,
                image_type=image_type,
                operation_type=OperationType.GENERATE_IMAGE,
                final_prompt=final_prompt,
                model_id=model_id,
                unit_cost=unit_cost,
                render_tier=render_tier,
                ratio=request.ratio,
                size=size,
                quality=(
                    "high"
                    if image_type == "卖点" and overlay_texts
                    else None
                ),
                seed=index - 1,
                references=references,
            )
            for index, (image_type, final_prompt) in enumerate(prompts, start=1)
        )
        job = ListingJobStart(
            job_id=job_id,
            user_id=user_id,
            prompt=request.prompt,
            modifiers=dict(request.modifiers),
            ratio=request.ratio,
            size=f"{size[0]}x{size[1]}",
            n=len(items),
            upload_keys=tuple(request.upload_ids),
            category=request.category,
        )
        return self._submission(
            job=job,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            items=items,
            fingerprint_payload={
                "operation_type": "generate",
                "request": request.model_dump(mode="json"),
                "model": model_id,
                "render_tier": render_tier.value,
            },
        )

    def plan_clone(
        self,
        *,
        user_id: str,
        request: CloneRequest,
        job_id: str,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model_id: str,
        unit_cost: Decimal,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> JobSubmission:
        final_prompt = compose_clone_prompt(
            request.prompt,
            request.modifiers,
            self.modifier_registry,
            category=request.category,
            card_registry=self.card_registry,
            clone_registry=self.clone_registry,
            clone_mode=request.clone_mode,
        )
        size = generation_size(render_tier, request.ratio)
        keys = (*request.product_upload_ids, *request.reference_upload_ids)
        roles = ("product",) + ("reference",) * len(request.reference_upload_ids)
        references = tuple(
            ReferenceSnapshot(
                source=ReferenceSource.UPLOAD,
                object_key=key,
                role=role,
                order=index,
            )
            for index, (key, role) in enumerate(zip(keys, roles, strict=True))
        )
        item = self._item(
            sequence=1,
            image_type=None,
            operation_type=OperationType.CLONE_IMAGE,
            final_prompt=final_prompt,
            model_id=model_id,
            unit_cost=unit_cost,
            render_tier=render_tier,
            ratio=request.ratio,
            size=size,
            quality=None,
            seed=0,
            references=references,
        )
        job = ListingJobStart(
            job_id=job_id,
            user_id=user_id,
            prompt=request.prompt,
            modifiers=dict(request.modifiers),
            ratio=request.ratio,
            size=f"{size[0]}x{size[1]}",
            n=1,
            upload_keys=keys,
            clone_mode=request.clone_mode,
            input_roles=roles,
            category=request.category,
        )
        return self._submission(
            job=job,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            items=(item,),
            fingerprint_payload={
                "operation_type": "clone",
                "request": request.model_dump(mode="json"),
                "model": model_id,
                "render_tier": render_tier.value,
            },
        )

    def plan_edit(
        self,
        *,
        user_id: str,
        request: EditRequest,
        source: GeneratedImageSource,
        job_id: str,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model_id: str,
        unit_cost: Decimal,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> JobSubmission:
        ratio = request.ratio or source.parent_ratio
        effective_modifiers = {**source.parent_modifiers, **request.modifiers}
        final_prompt = compose_edit_prompt(
            request.prompt,
            effective_modifiers,
            self.modifier_registry,
            edit_registry=self.edit_registry,
            edit_mode=request.edit_mode,
        )
        size = generation_size(render_tier, ratio)
        references = (
            ReferenceSnapshot(
                source=ReferenceSource.GENERATED,
                object_key=request.source_image_key,
                role="source",
                order=0,
            ),
            *(
                ReferenceSnapshot(
                    source=ReferenceSource.UPLOAD,
                    object_key=key,
                    role="product",
                    order=index,
                )
                for index, key in enumerate(
                    source.root_product_upload_keys, start=1
                )
            ),
        )
        item = self._item(
            sequence=1,
            image_type=None,
            operation_type=OperationType.EDIT_IMAGE,
            final_prompt=final_prompt,
            model_id=model_id,
            unit_cost=unit_cost,
            render_tier=render_tier,
            ratio=ratio,
            size=size,
            quality=None,
            seed=0,
            references=references,
        )
        job = ListingJobStart(
            job_id=job_id,
            user_id=user_id,
            prompt=request.prompt,
            modifiers=effective_modifiers,
            ratio=ratio,
            size=f"{size[0]}x{size[1]}",
            n=1,
            upload_keys=source.root_product_upload_keys,
            input_roles=("product",) * len(source.root_product_upload_keys),
            parent_job_id=source.parent_job_id,
            source_image_key=request.source_image_key,
            edit_mode=request.edit_mode,
        )
        return self._submission(
            job=job,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            items=(item,),
            fingerprint_payload={
                "operation_type": "edit",
                "request": request.model_dump(mode="json"),
                "source": asdict(source),
                "model": model_id,
                "render_tier": render_tier.value,
            },
        )

    def plan_background_replace(
        self,
        *,
        user_id: str,
        request: BackgroundReplaceRequest,
        source: GeneratedImageSource | None,
        ratio: str,
        job_id: str,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        model_id: str,
        unit_cost: Decimal,
        render_tier: RenderTier = RenderTier.STANDARD,
    ) -> JobSubmission:
        upload_keys: list[str] = []
        input_roles: list[str] = []
        if request.source.kind == "generated":
            if source is None:
                raise ValueError("generated source context is required")
            references = [
                ReferenceSnapshot(
                    source=ReferenceSource.GENERATED,
                    object_key=request.source.image_key,
                    role="source",
                    order=0,
                )
            ]
            parent_job_id = source.parent_job_id
            source_image_key = request.source.image_key
        else:
            if source is not None:
                raise ValueError("upload source must not have generated context")
            references = [
                ReferenceSnapshot(
                    source=ReferenceSource.UPLOAD,
                    object_key=request.source.upload_id,
                    role="product",
                    order=0,
                )
            ]
            upload_keys.append(request.source.upload_id)
            input_roles.append("product")
            parent_job_id = None
            source_image_key = None
        if request.background.kind == "reference":
            references.append(
                ReferenceSnapshot(
                    source=ReferenceSource.UPLOAD,
                    object_key=request.background.upload_id,
                    role="background",
                    order=1,
                )
            )
            upload_keys.append(request.background.upload_id)
            input_roles.append("background")

        final_prompt = compose_background_replace_prompt(request.background)
        size = generation_size(render_tier, ratio)
        item = self._item(
            sequence=1,
            image_type=None,
            operation_type=OperationType.REPLACE_BACKGROUND,
            final_prompt=final_prompt,
            model_id=model_id,
            unit_cost=unit_cost,
            render_tier=render_tier,
            ratio=ratio,
            size=size,
            quality=None,
            seed=0,
            references=tuple(references),
        )
        user_prompt = (
            request.background.description
            if request.background.kind == "description"
            else request.background.instruction
        )
        job = ListingJobStart(
            job_id=job_id,
            user_id=user_id,
            prompt=user_prompt,
            modifiers={},
            ratio=ratio,
            size=f"{size[0]}x{size[1]}",
            n=1,
            upload_keys=tuple(upload_keys),
            input_roles=tuple(input_roles),
            parent_job_id=parent_job_id,
            source_image_key=source_image_key,
        )
        return self._submission(
            job=job,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
            request_id=request_id,
            items=(item,),
            fingerprint_payload={
                "operation_type": "background_replace",
                "request": request.model_dump(mode="json"),
                "source": asdict(source) if source is not None else None,
                "ratio": ratio,
                "model": model_id,
                "render_tier": render_tier.value,
            },
        )

    def _item(
        self,
        *,
        sequence: int,
        image_type: str | None,
        operation_type: OperationType,
        final_prompt: str,
        model_id: str,
        unit_cost: Decimal,
        render_tier: RenderTier,
        ratio: str,
        size: tuple[int, int],
        quality: str | None,
        seed: int,
        references: tuple[ReferenceSnapshot, ...],
    ) -> GenerationItemSpec:
        return GenerationItemSpec(
            item_id=uuid4().hex,
            operation_id=uuid4().hex,
            sequence=sequence,
            image_type=image_type,
            operation_type=operation_type,
            render_tier=render_tier,
            final_prompt=final_prompt,
            model=model_id,
            ratio=ratio,
            size=size,
            quality=quality,
            seed=seed,
            references=references,
            reserved_cost=unit_cost,
        )

    @staticmethod
    def _submission(
        *,
        job: ListingJobStart,
        idempotency_key: str,
        trace_id: str,
        request_id: str,
        items: tuple[GenerationItemSpec, ...],
        fingerprint_payload: dict[str, object],
    ) -> JobSubmission:
        return JobSubmission(
            job=job,
            idempotency_key=idempotency_key,
            request_fingerprint=_fingerprint(fingerprint_payload),
            items=items,
            trace_id=trace_id,
            request_id=request_id,
        )
