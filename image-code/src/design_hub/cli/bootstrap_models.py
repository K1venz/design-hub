"""Import legacy model credentials into the verified live-model registry once."""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from design_hub.application.admin.model_capability_service import (
    LiveCapabilityProviderFactory,
    ModelCapabilityService,
)
from design_hub.application.admin.model_config_service import (
    CiphertextCredentials,
    ModelConfigService,
)
from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelType, ProviderType
from design_hub.domain.model_config import DOUBAO_CHAT, GPT_IMAGE_2, WAN_2_7_IMAGE_PRO
from design_hub.infrastructure.db.model_call_repo import SqlAlchemyModelCallRecorder
from design_hub.infrastructure.db.model_config_repo import SqlAlchemyModelConfigRepository
from design_hub.infrastructure.db.session import create_engine, create_session_factory
from design_hub.infrastructure.security.model_verification import (
    PyJwtModelVerificationService,
)
from design_hub.infrastructure.security.rsa_secret_cipher import RsaSecretCipher

_BOOTSTRAP_ACTOR_ID = 0
_MAX_CSV_BYTES = 64 * 1024
_MODEL_IDS = frozenset((GPT_IMAGE_2, WAN_2_7_IMAGE_PRO, DOUBAO_CHAT))
_WAN_API_HOST = "https://dashscope.aliyuncs.com"
_WAN_API_HOSTNAME = "dashscope.aliyuncs.com"
_WAN_API_PATH = "/api/v1"
_WAN_CSV_FIELDS = frozenset(("apiKey", "apiHost", "dashScope"))


class BootstrapInputError(ValueError):
    """A deliberately detail-free bootstrap input error."""

    def __init__(self) -> None:
        super().__init__("invalid bootstrap input")


class BootstrapModelFailed(RuntimeError):
    """A deliberately detail-free failure for one fixed platform model ID."""

    def __init__(self, model_id: str) -> None:
        if model_id not in _MODEL_IDS:
            raise ValueError("invalid bootstrap model ID")
        self.model_id = model_id
        super().__init__(f"{model_id}: failure")


@dataclass(frozen=True)
class BootstrapModel:
    name: str
    display_name: str
    model_type: ModelType
    provider_type: ProviderType
    base_url: str
    model: str
    credentials: CiphertextCredentials = field(repr=False)
    extra: dict[str, object]
    make_default: bool = False


@dataclass(frozen=True)
class BootstrapPlan:
    cipher: RsaSecretCipher = field(repr=False)
    models: tuple[BootstrapModel, ...] = field(repr=False)


@dataclass(frozen=True)
class ModelBootstrap:
    configs: ModelConfigService
    capabilities: ModelCapabilityService
    actor_id: int

    async def run(
        self,
        models: Sequence[BootstrapModel],
        *,
        report: Callable[[str, bool], None],
    ) -> None:
        for model in models:
            try:
                current = await self.configs.repo.get(model.name)
                if current is None or current.enabled:
                    raise ValueError("model is not a disabled bootstrap skeleton")
                tested = await self.capabilities.test(
                    manager_id=str(self.actor_id),
                    name=model.name,
                    model_type=model.model_type,
                    provider_type=model.provider_type,
                    base_url=model.base_url,
                    model=model.model,
                    credentials=model.credentials,
                    extra=model.extra,
                )
                await self.configs.update(
                    actor_id=self.actor_id,
                    name=model.name,
                    display_name=model.display_name,
                    model_type=model.model_type,
                    provider_type=model.provider_type,
                    base_url=model.base_url,
                    model=model.model,
                    credentials=model.credentials,
                    enabled=True,
                    extra=model.extra,
                    verification_proof=tested.verification_proof,
                )
                if model.make_default:
                    await self.configs.set_default(
                        actor_id=self.actor_id,
                        name=model.name,
                    )
            except Exception:
                report(model.name, False)
                raise BootstrapModelFailed(model.name) from None
            report(model.name, True)


def load_bootstrap_plan(
    *,
    wan_csv: Path,
    environ: Mapping[str, str] | None = None,
) -> BootstrapPlan:
    values = os.environ if environ is None else environ
    try:
        cipher = RsaSecretCipher.from_pem(
            _required_environment(values, "AUTH_RSA_PRIVATE_KEY_PEM")
        )
        standard_api_keys = _standard_api_keys(
            _required_environment(values, "GPT_IMAGE_API_KEY")
        )
        gpt_credentials: CiphertextCredentials = {
            "standard_api_keys": [
                cipher.encrypt(api_key) for api_key in standard_api_keys
            ],
            "four_k_api_key": cipher.encrypt(
                _required_environment(values, "GPT_IMAGE_4K_API_KEY")
            ),
        }
        chat_credentials: CiphertextCredentials = {
            "api_key": cipher.encrypt(
                _required_environment(values, "TEXT_LLM_API_KEY")
            )
        }
        wan = _read_wan_csv(wan_csv)
        wan_credentials: CiphertextCredentials = {
            "api_key": cipher.encrypt(wan["apiKey"])
        }
        gpt_extra = _gpt_extra(values)
        chat_extra: dict[str, object] = {
            "thinking_disabled": _environment_bool(
                values,
                "TEXT_LLM_THINKING_DISABLED",
                default=False,
            )
        }
        models = (
            BootstrapModel(
                name=GPT_IMAGE_2,
                display_name="GPT Image 2.0",
                model_type=ModelType.IMAGE,
                provider_type=ProviderType.OPENAI_COMPAT_IMAGE,
                base_url=_required_environment(values, "GPT_IMAGE_BASE_URL"),
                model=_required_environment(values, "GPT_IMAGE_MODEL"),
                credentials=gpt_credentials,
                extra=gpt_extra,
                make_default=True,
            ),
            BootstrapModel(
                name=WAN_2_7_IMAGE_PRO,
                display_name="Wan 2.7 Image Pro",
                model_type=ModelType.IMAGE,
                provider_type=ProviderType.DASHSCOPE_WAN_IMAGE,
                base_url=_wan_base_url(wan["apiHost"], wan["dashScope"]),
                model=WAN_2_7_IMAGE_PRO,
                credentials=wan_credentials,
                extra={"watermark": False},
            ),
            BootstrapModel(
                name=DOUBAO_CHAT,
                display_name="Doubao Chat",
                model_type=ModelType.CHAT,
                provider_type=ProviderType.OPENAI_COMPAT_CHAT,
                base_url=_required_environment(values, "TEXT_LLM_BASE_URL"),
                model=_required_environment(values, "TEXT_LLM_MODEL"),
                credentials=chat_credentials,
                extra=chat_extra,
                make_default=True,
            ),
        )
    except BootstrapInputError:
        raise
    except Exception:
        raise BootstrapInputError() from None
    return BootstrapPlan(cipher=cipher, models=models)


async def execute_bootstrap(
    plan: BootstrapPlan,
    *,
    report: Callable[[str, bool], None],
) -> None:
    settings = Settings()
    engine = create_engine(settings.db_url)
    try:
        sessions = create_session_factory(engine)
        repository = SqlAlchemyModelConfigRepository(sessions)
        verifier = PyJwtModelVerificationService(
            secret=settings.jwt_secret.get_secret_value(),
            ttl_seconds=settings.model_verification_ttl_seconds,
        )
        configs = ModelConfigService(
            repo=repository,
            cipher=plan.cipher,
            verifier=verifier,
        )
        capabilities = ModelCapabilityService(
            repository=repository,
            cipher=plan.cipher,
            verifier=verifier,
            providers=LiveCapabilityProviderFactory(
                recorder=SqlAlchemyModelCallRecorder(sessions),
                settings=settings,
            ),
        )
        await ModelBootstrap(
            configs=configs,
            capabilities=capabilities,
            actor_id=_BOOTSTRAP_ACTOR_ID,
        ).run(plan.models, report=report)
    finally:
        await engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Securely bootstrap verified live-model credentials once."
    )
    parser.add_argument("--wan-csv", required=True)
    args = parser.parse_args(argv)
    try:
        plan = load_bootstrap_plan(
            wan_csv=Path(args.wan_csv),
            environ=environ,
        )
        asyncio.run(execute_bootstrap(plan, report=_print_status))
    except BootstrapModelFailed:
        return 1
    except Exception:
        print("bootstrap: failure", file=sys.stderr)
        return 1
    return 0


def _required_environment(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if value is None or not value.strip():
        raise BootstrapInputError()
    return value.strip()


def _standard_api_keys(value: str) -> tuple[str, ...]:
    keys = tuple(part.strip() for part in value.split(","))
    if not keys or any(not key for key in keys):
        raise BootstrapInputError()
    return keys


def _gpt_extra(values: Mapping[str, str]) -> dict[str, object]:
    extra: dict[str, object] = {}
    for environment_name, field_name, default in (
        ("GPT_IMAGE_INPUT_FIDELITY", "input_fidelity", "high"),
        ("GPT_IMAGE_RESPONSE_FORMAT", "response_format", "b64_json"),
    ):
        value = values.get(environment_name, default).strip()
        if value:
            extra[field_name] = value
    return extra


def _environment_bool(
    values: Mapping[str, str],
    name: str,
    *,
    default: bool,
) -> bool:
    raw = values.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise BootstrapInputError()


def _read_wan_csv(path: Path) -> dict[str, str]:
    resolved = _safe_csv_path(path)
    try:
        if resolved.stat().st_size > _MAX_CSV_BYTES:
            raise BootstrapInputError()
        with resolved.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, strict=True))
    except BootstrapInputError:
        raise
    except (OSError, UnicodeError, csv.Error):
        raise BootstrapInputError() from None
    if rows and tuple(cell.strip().lower() for cell in rows[0]) == (
        "key",
        "value",
    ):
        rows = rows[1:]
    parsed: dict[str, str] = {}
    for row in rows:
        if len(row) != 2:
            raise BootstrapInputError()
        key, value = (cell.strip() for cell in row)
        if not key or not value or key in parsed:
            raise BootstrapInputError()
        parsed[key] = value
    if frozenset(parsed) != _WAN_CSV_FIELDS:
        raise BootstrapInputError()
    return parsed


def _safe_csv_path(path: Path) -> Path:
    try:
        if not path.is_absolute():
            raise BootstrapInputError()
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise BootstrapInputError()
        repository_root = _repository_root()
        if repository_root is not None and resolved.is_relative_to(repository_root):
            raise BootstrapInputError()
        return resolved
    except BootstrapInputError:
        raise
    except OSError:
        raise BootstrapInputError() from None


def _repository_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return None


def _wan_base_url(api_host: str, dashscope_path: str) -> str:
    try:
        parsed = urlsplit(api_host.strip())
        port = parsed.port
    except ValueError:
        raise BootstrapInputError() from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != _WAN_API_HOSTNAME
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or dashscope_path.strip() != _WAN_API_PATH
    ):
        raise BootstrapInputError()
    return f"{_WAN_API_HOST}{_WAN_API_PATH}"


def _print_status(model_id: str, succeeded: bool) -> None:
    if model_id not in _MODEL_IDS:
        raise ValueError("invalid bootstrap model ID")
    status = "success" if succeeded else "failure"
    print(f"{model_id}: {status}")


if __name__ == "__main__":
    raise SystemExit(main())
