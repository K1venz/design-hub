"""密码哈希端口（DIP，ISSUE-0015）。application 只依赖抽象，bcrypt 落 infrastructure。"""

from abc import ABC, abstractmethod


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: str) -> str:
        ...

    @abstractmethod
    def verify(self, password: str, hashed: str) -> bool:
        ...
