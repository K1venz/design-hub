def image_key_from_url(url: str) -> str:
    """出图 url → 存储 key（文件名）。

    兼容 /img/<sha>.png、https://host/img/<sha>.png、TOS 预签名 url(<sha>.png?X-Tos-…)：
    先去 ?query 再取末段文件名。**存 key 不存 url**：切 OSS / 签名 url 过期都不影响（读时再签）。
    """
    return url.split("?")[0].rsplit("/", 1)[-1]
