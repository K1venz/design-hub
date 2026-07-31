from dataclasses import dataclass
from decimal import Decimal

from design_hub.ports.model_calls import ModelCallContext, ModelUsage


@dataclass(frozen=True)
class StartedCall:
    call_id: str
    context: ModelCallContext
    provider: str
    model: str
    attempt_no: int


@dataclass(frozen=True)
class FinishedCall:
    call_id: str
    usage: ModelUsage
    provider_request_id: str | None
    platform_cost: Decimal | None
    diagnostic_code: str | None


@dataclass(frozen=True)
class FailedCall:
    call_id: str
    code: str
    detail: str


class RecordingModelCallRecorder:
    def __init__(self, *, start_error: Exception | None = None) -> None:
        self.start_error = start_error
        self.started: list[StartedCall] = []
        self.succeeded: list[FinishedCall] = []
        self.failed: list[FailedCall] = []
        self.uncertain_calls: list[tuple[str, str]] = []
        self.interrupted: list[str] = []

    async def start(
        self,
        *,
        context: ModelCallContext,
        provider: str,
        model: str,
        attempt_no: int,
    ) -> str:
        if self.start_error is not None:
            raise self.start_error
        call_id = f"call-{len(self.started) + 1}"
        self.started.append(
            StartedCall(
                call_id=call_id,
                context=context,
                provider=provider,
                model=model,
                attempt_no=attempt_no,
            )
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
        self.succeeded.append(
            FinishedCall(
                call_id=call_id,
                usage=usage,
                provider_request_id=provider_request_id,
                platform_cost=platform_cost,
                diagnostic_code=diagnostic_code,
            )
        )

    async def fail(self, call_id: str, *, code: str, detail: str) -> None:
        self.failed.append(FailedCall(call_id=call_id, code=code, detail=detail))

    async def uncertain(self, call_id: str, *, detail: str) -> None:
        self.uncertain_calls.append((call_id, detail))

    async def interrupt(self, call_id: str) -> None:
        self.interrupted.append(call_id)
