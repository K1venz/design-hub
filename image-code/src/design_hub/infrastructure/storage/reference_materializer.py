from dataclasses import dataclass

from design_hub.application.listing.upload_service import UploadService
from design_hub.domain.models import ReferenceImage
from design_hub.domain.tasking import ReferenceSource
from design_hub.ports.generation_work import GenerationWorkItem
from design_hub.ports.image_store import ImageStore
from design_hub.ports.media_url_signer import MediaUrlSigner
from design_hub.ports.model_provider import ReferenceMode


@dataclass(frozen=True)
class StoredReferenceMaterializer:
    uploads: UploadService
    images: ImageStore
    signer: MediaUrlSigner

    async def materialize(
        self,
        work: GenerationWorkItem,
        reference_mode: ReferenceMode,
    ) -> tuple[ReferenceImage, ...]:
        references: list[ReferenceImage] = []
        for snapshot in sorted(
            work.spec.references,
            key=lambda value: value.order,
        ):
            if reference_mode == "url":
                url = (
                    self.signer.upload_url(snapshot.object_key)
                    if snapshot.source is ReferenceSource.UPLOAD
                    else self.signer.generated_url(snapshot.object_key)
                )
                references.append(ReferenceImage(url=url))
                continue
            data = (
                (await self.uploads.load(snapshot.object_key))[0]
                if snapshot.source is ReferenceSource.UPLOAD
                else await self.images.load(snapshot.object_key)
            )
            references.append(ReferenceImage(data=data))
        return tuple(references)
