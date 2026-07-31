from abc import ABC, abstractmethod

from design_hub.domain.enums import ModelType


class ModelVerificationService(ABC):
    """Issues and verifies opaque proofs for one tested model connection."""

    @abstractmethod
    def issue(
        self,
        *,
        manager_id: str,
        model_id: str,
        model_type: ModelType,
        fingerprint: str,
    ) -> str:
        ...

    @abstractmethod
    def verify(
        self,
        proof: str,
        *,
        manager_id: str,
        model_id: str,
        model_type: ModelType,
        fingerprint: str,
    ) -> None:
        """Raise ValueError when the opaque proof does not match this connection."""
        ...
