from design_hub.domain.errors import AuthenticationError
from design_hub.domain.models import OAuthProfile
from design_hub.ports.auth import OAuthClient


class MockOAuthClient(OAuthClient):
    """开发/测试用 mock OAuth（不联网）。按 code 前缀约定映射部门，便于 mint 各角色令牌：

    - `mgr-*`  → 部门「管理层」（→ 管理者）
    - `out-*`  → 部门「其他」（→ 登录被拒 403）
    - 其余     → 部门「设计部」（→ 设计师）

    真实飞书/钉钉 OAuth 待用户提供 app 凭据后由对应适配器替换（LSP）。
    """

    async def exchange(self, code: str) -> OAuthProfile:
        if not code.strip():
            raise AuthenticationError("缺少授权 code")
        if code.startswith("mgr-"):
            dept = "管理层"
        elif code.startswith("out-"):
            dept = "其他"
        else:
            dept = "设计部"
        return OAuthProfile(user_id=code, name=code, dept=dept)
