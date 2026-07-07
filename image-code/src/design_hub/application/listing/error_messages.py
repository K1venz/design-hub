"""出图失败异常 → 用户话术映射（ISSUE-0055 (ii)）。

provider 原始技术错（如 `gpt-image-2 500: {"error":…traceid…}`）绝不直吐用户；
在 error 落库/发事件处过本层映射，原始错保留进日志（不进用户面）。分层同 513ca0b。
"""

from design_hub.domain.errors import DomainError
from design_hub.ports.model_provider import ProviderError, ProviderTimeout


def humanize_image_error(exc: BaseException) -> str:
    """出图异常 → 用户可读文案（不含 traceid/HTTP 码/英文栈）。

    顺序按异常类型特化度：ProviderTimeout(5xx/429/超时/网络) → provider 4xx(裸 DomainError)
    → 其余 ProviderError(未返回图/数量不足) → 领域错子类(自带用户话术) → 未预期兜底。
    """
    if isinstance(exc, ProviderTimeout):  # 429/5xx/超时/网络：瞬时或上游故障
        return "图像服务临时繁忙，请稍后重试"
    if type(exc) is DomainError:  # provider 4xx（裸 DomainError；鉴权/配置/坏请求）
        return "图像服务暂不可用，请稍后重试"
    if isinstance(exc, ProviderError):  # 未返回图/数量不足等契约异常
        return "图像服务暂时未能出图，请稍后重试"
    if isinstance(exc, DomainError):  # BudgetExceeded/NotFoundError 等：自带用户话术
        return str(exc)
    return "图像出错，请稍后重试"  # 未预期异常兜底：不泄漏原始技术文本
