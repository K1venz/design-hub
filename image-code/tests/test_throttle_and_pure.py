"""上传对象所有权纯函数单测。"""

from design_hub.ports.upload_store import owns, upload_ns


def test_owns_is_namespace_prefixed() -> None:
    ns = upload_ns("user-7")
    assert owns(f"{ns}/abc.png", "user-7")
    assert not owns(f"{ns}/abc.png", "user-8")  # 越权
    assert not owns("abc.png", "user-7")  # 无命名空间
