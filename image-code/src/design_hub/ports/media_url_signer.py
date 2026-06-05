from abc import ABC, abstractmethod


class MediaUrlSigner(ABC):
    """把存储 key 解析成前端可访问的 url（端口）。

    私有桶下 url 不能静态拼、要按请求签：本地实现=静态拼接（nginx /img），
    TOS 实现=预签名 url（pre-signed GET，会过期）。出图结果与上传图分属两桶，各签各的。
    """

    @abstractmethod
    def generated_url(self, key: str) -> str:
        """出图结果图 image_key → 可访问 url。"""
        ...

    @abstractmethod
    def upload_url(self, key: str) -> str:
        """上传图 upload_key → 可访问 url。"""
        ...
