"""出图失败异常 → 用户话术映射（ISSUE-0055 (ii)）：分桶正确 + 绝不泄漏原始技术文本。"""

from design_hub.application.listing.error_messages import humanize_image_error
from design_hub.domain.errors import BudgetExceeded, DomainError
from design_hub.ports.model_provider import ProviderError, ProviderTimeout


def test_provider_timeout_5xx_maps_to_busy_and_hides_raw() -> None:
    # 上游 5xx/429/超时/网络 → 繁忙话术；原始 500/traceid/模型名不泄漏
    exc = ProviderTimeout("gpt-image-2 500: prepare chat requirements error (traceid=abc)")
    msg = humanize_image_error(exc)
    assert msg == "图像服务临时繁忙，请稍后重试"
    assert "500" not in msg and "traceid" not in msg and "gpt-image-2" not in msg


def test_provider_4xx_bare_domain_error_maps_to_unavailable() -> None:
    # provider 4xx（裸 DomainError，鉴权/配置）→ 暂不可用；不泄漏 401/token 报文
    exc = DomainError("gpt-image-2 401 (不切备): Invalid token")
    msg = humanize_image_error(exc)
    assert msg == "图像服务暂不可用，请稍后重试"
    assert "401" not in msg and "token" not in msg.lower()


def test_bare_provider_error_maps_to_generic_retry() -> None:
    exc = ProviderError("gpt-image-2 未返回任何图片，请重试")
    assert humanize_image_error(exc) == "图像服务暂时未能出图，请稍后重试"


def test_domain_subclass_passthrough_keeps_user_message() -> None:
    # 领域错子类（BudgetExceeded/NotFoundError）自带用户话术 → 原样透传（非 provider 技术错）
    assert humanize_image_error(BudgetExceeded("余额不足，请充值")) == "余额不足，请充值"


def test_unexpected_exception_falls_back_without_leak() -> None:
    # 未预期异常（DB 抖断/编码 bug 等）→ 兜底话术，绝不把 repr/栈吐给用户
    exc = RuntimeError("DB 抖断（add_images）")
    msg = humanize_image_error(exc)
    assert msg == "图像出错，请稍后重试"
    assert "DB" not in msg and "add_images" not in msg
