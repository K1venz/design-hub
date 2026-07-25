"""listing 出图任务启动器（application 层单一事实源）。

把「同步 fail-fast 校验 → upload 归属校验/载图 → 频控 acquire → 建 Command → 入队」
这条链从三个路由内联处抽出，路由（interface）与 ChatOrchestrator（application）**共调同一实现**
（#884⑤：工具执行走同一 service + 完整校验链，不 HTTP 自调用、不绕 interface 校验）。

行为与既有路由逐字对齐（零回归底线，ISSUE-0047 待验证期）：校验顺序、错误类型、
Command 字段、频控时机、job_id 生成全部不变。入参 = 已解析的 pydantic 请求 DTO
（extra=forbid 等约束在解析时已生效）。
"""

import uuid
from dataclasses import dataclass

from design_hub.application.listing.commands import (
    CloneCommand,
    EditCommand,
    ListingGenerationCommand,
)
from design_hub.application.listing.listing_service import (
    ListingGenerationService,
    build_listing_prompts,
)
from design_hub.application.listing.prompt_composer import (
    compose_clone_prompt,
    compose_edit_prompt,
)
from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.listing.sizing import generation_size, ratio_to_size
from design_hub.application.listing.upload_service import UploadService
from design_hub.application.rate_limit import ThrottledCommand, UserRateLimiter
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import NotFoundError
from design_hub.domain.models import AuthUser, ReferenceImage
from design_hub.ports.events import EventPublisher
from design_hub.ports.image_store import ImageStore
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.listing_query import ListingHistoryQuery
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.model_provider import ReferenceMode
from design_hub.ports.task_queue import TaskQueue
from design_hub.ports.upload_store import owns


@dataclass
class ListingJobLauncher:
    """三条出图路径（generate/clone/edit）的统一启动器。返回 job_id。"""

    service: ListingGenerationService
    uploads: UploadService
    rate_limiter: UserRateLimiter
    events: EventPublisher
    history: ListingHistory
    queue: TaskQueue
    query: ListingHistoryQuery
    image_store: ImageStore
    media_signer: MediaUrlSigner  # 参考图现签 URL（ISSUE-0065 异步模态；同步模态不用）

    async def _ref_from_upload(self, upload_key: str, mode: ReferenceMode) -> ReferenceImage:
        """上传桶参考图 → ReferenceImage：url 模态签公网 URL（不载字节，worker 回拉）；
        bytes 模态载字节走 multipart（ISSUE-0065）。"""
        if mode == "url":
            return ReferenceImage(url=self.media_signer.upload_url(upload_key))
        return ReferenceImage(data=(await self.uploads.load(upload_key))[0])

    async def _ref_from_generated(self, image_key: str, mode: ReferenceMode) -> ReferenceImage:
        """出图桶参考图（编辑源图）→ ReferenceImage。
        url 模态签 generated_url（不载字节）；bytes 模态读回字节。"""
        if mode == "url":
            return ReferenceImage(url=self.media_signer.generated_url(image_key))
        return ReferenceImage(data=await self.image_store.load(image_key))

    def validate(
        self, user: AuthUser, req: ListingGenerateRequest | CloneRequest | EditRequest
    ) -> None:
        """出图前**纯校验**（无副作用：数量/比例/枚举/图型卡/owner 前缀）——launch_* 与
        ChatOrchestrator 费用确认前预检共用（#884⑤ 单一校验源）。edit 的源图反解(DB 只读)
        在 launch 时做，本方法只校验 edit 的纯参数（档位 / delta-ratio 冲突）。"""
        if isinstance(req, ListingGenerateRequest):
            if not 1 <= len(req.upload_ids) <= 3:
                raise ValueError(f"请上传 1–3 张图片（当前 {len(req.upload_ids)} 张）")
            ratio_to_size(req.ratio)
            overlay = tuple(req.overlay_texts) if req.overlay_texts else ()
            build_listing_prompts(
                req.prompt, req.modifiers, self.service.modifier_registry,
                self.service.card_registry, self.service.type_registry,
                category=req.category, n=req.n, plan=req.plan, overlay_texts=overlay,
            )
            for uid in req.upload_ids:
                if not owns(uid, user.user_id):
                    raise NotFoundError("有产品图找不到或无权访问，请重新上传后再试")
        elif isinstance(req, CloneRequest):
            if len(req.product_upload_ids) != 1:
                raise ValueError(f"复刻需要 1 张产品图（当前 {len(req.product_upload_ids)} 张）")
            if not 1 <= len(req.reference_upload_ids) <= 2:
                raise ValueError(
                    f"请上传 1–2 张爆款参考图（当前 {len(req.reference_upload_ids)} 张）"
                )
            ratio_to_size(req.ratio)
            compose_clone_prompt(
                req.prompt, req.modifiers, self.service.modifier_registry,
                category=req.category, card_registry=self.service.card_registry,
                clone_registry=self.service.clone_registry, clone_mode=req.clone_mode,
            )
            for uid in [*req.product_upload_ids, *req.reference_upload_ids]:
                if not owns(uid, user.user_id):
                    raise NotFoundError("有图片找不到或无权访问，请重新上传后再试")
        else:  # EditRequest
            self.service.edit_registry.block(req.edit_mode)  # 未知档位 → 400
            if req.edit_mode == "delta" and req.ratio is not None:
                raise ValueError("微调会沿用原图比例，如需修改比例请改用「重做」")

    async def launch_generate(
        self,
        user: AuthUser,
        req: ListingGenerateRequest,
        *,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> str:
        """listing 出图（单图 n / 套图 plan 互斥，PRD §3.12.14）：入队返回 job_id。"""
        # 边界 fail-fast（ISSUE-0024）：入队前同步校验完所有输入，任一非法 → 4xx，不入队。
        self.validate(user, req)
        generation_size(model, req.ratio)
        overlay = tuple(req.overlay_texts) if req.overlay_texts else ()
        # 参考图按 provider 模态物化（ISSUE-0065）：url 模态签公网 URL、bytes 模态载字节。
        # load() 对非法格式→400、缺文件→404（url 模态下 owner 校验已在 validate 完成）。
        mode = self.service.reference_mode(model)
        images = tuple([await self._ref_from_upload(uid, mode) for uid in req.upload_ids])
        self.rate_limiter.acquire(user.user_id)  # 频控（A-4）：5 单/分 + ≤2 in-flight，超限 429
        job_id = uuid.uuid4().hex
        command = ListingGenerationCommand(
            service=self.service,
            events=self.events,
            history=self.history,
            user_id=user.user_id,
            prompt=req.prompt,
            modifiers=req.modifiers,
            images=images,
            upload_keys=tuple(req.upload_ids),
            ratio=req.ratio,
            n=req.n,
            plan=req.plan,
            overlay_texts=overlay,
            category=req.category,
            model=model,
        )
        throttled = ThrottledCommand(
            inner=command, limiter=self.rate_limiter, user_id=user.user_id
        )
        await self.queue.enqueue(job_id=job_id, command=throttled)
        return job_id

    async def launch_clone(
        self,
        user: AuthUser,
        req: CloneRequest,
        *,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> str:
        """爆款图复刻（PRD §3.13）：产品图==1 + 爆款参考图 1..2，两档复刻，返回 job_id。"""
        # 边界 fail-fast（ISSUE-0024 口径）：入队前同步校验完所有输入。
        self.validate(user, req)
        generation_size(model, req.ratio)
        ordered_ids = [*req.product_upload_ids, *req.reference_upload_ids]  # 产品前·参考后=角色契约
        mode = self.service.reference_mode(model)  # 参考图模态物化（ISSUE-0065）
        loaded = [await self._ref_from_upload(uid, mode) for uid in ordered_ids]
        self.rate_limiter.acquire(user.user_id)  # 频控（A-4）：与 generate 同闸（计费动作统一限）
        job_id = uuid.uuid4().hex
        command = CloneCommand(
            service=self.service,
            events=self.events,
            history=self.history,
            user_id=user.user_id,
            prompt=req.prompt,
            modifiers=req.modifiers,
            product_image=loaded[0],
            reference_images=tuple(loaded[1:]),
            upload_keys=tuple(ordered_ids),
            ratio=req.ratio,
            category=req.category,
            clone_mode=req.clone_mode,
            model=model,
        )
        throttled = ThrottledCommand(
            inner=command, limiter=self.rate_limiter, user_id=user.user_id
        )
        await self.queue.enqueue(job_id=job_id, command=throttled)
        return job_id

    async def launch_edit(
        self,
        user: AuthUser,
        req: EditRequest,
        *,
        model: ModelName = ModelName.GPT_IMAGE_2,
    ) -> str:
        """二次编辑（PRD §3.12.13/ISSUE-0040）：基于本人产出图迭代（delta 微调 / full 重做）。

        源图=唯一不透明 handle（source_image_key），owner/parent 链全部服务端反解；
        喂图=[源图, 链根产品锚 1..3]（D2：每轮锚链根原图，漂移不随轮数叠加）。
        """
        self.validate(user, req)  # 档位 + delta/ratio 冲突（纯校验）；源图反解在下（DB 只读）
        # 反解源图（E-δ）：本人∧成功∧最新行 → 父上下文 + 链根产品锚；任一环不满足 → 404 防枚举
        source = await self.query.resolve_edit_source(
            source_image_key=req.source_image_key, user_id=user.user_id
        )
        if source is None:
            raise NotFoundError(f"源图不存在或无权访问：{req.source_image_key}")
        ratio = req.ratio if req.ratio is not None else source.parent_ratio  # full 显式可覆盖
        generation_size(model, ratio)
        # modifiers 叠新（R3）：父语境为底、本轮覆盖；组装与落库同用 effective（每单自包含）。
        # 继承值同样过 registry：父历史值若已被收窄下架 → 400 如实报错，不静默剔除。
        effective = {**source.parent_modifiers, **req.modifiers}
        compose_edit_prompt(
            req.prompt, effective, self.service.modifier_registry,
            edit_registry=self.service.edit_registry, edit_mode=req.edit_mode,
        )
        # 载图按 provider 模态物化（ISSUE-0065）：源图=generate 桶、链根锚=uploads 桶
        # （keys 来自 DB 可信）；url 模态各签公网 URL 不载字节，bytes 模态各载字节。
        mode = self.service.reference_mode(model)
        source_image = await self._ref_from_generated(req.source_image_key, mode)
        anchors = tuple(
            [await self._ref_from_upload(k, mode) for k in source.root_product_upload_keys]
        )
        self.rate_limiter.acquire(user.user_id)  # 频控（A-4）：计费动作统一闸，超限 429
        job_id = uuid.uuid4().hex
        command = EditCommand(
            service=self.service,
            events=self.events,
            history=self.history,
            user_id=user.user_id,
            prompt=req.prompt,
            modifiers=effective,
            source_image=source_image,
            anchor_images=anchors,
            anchor_keys=source.root_product_upload_keys,
            parent_job_id=source.parent_job_id,
            source_image_key=req.source_image_key,
            ratio=ratio,
            edit_mode=req.edit_mode,
            model=model,
        )
        throttled = ThrottledCommand(
            inner=command, limiter=self.rate_limiter, user_id=user.user_id
        )
        await self.queue.enqueue(job_id=job_id, command=throttled)
        return job_id
