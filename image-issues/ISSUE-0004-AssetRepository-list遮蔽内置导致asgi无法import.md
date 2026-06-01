---
id: ISSUE-0004
title: AssetRepository.list 方法遮蔽内置 list，get_many 注解求值崩溃，asgi app 无法 import
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发        # WP-F 集成自检时发现
owner: QA             # 已修复待 QA 验证（球交回 QA）
created: 2026-06-01
updated: 2026-06-01
related:
  - code: image-code/src/design_hub/ports/repositories.py  # AssetRepository, line 92 / 96
  - WP: WP-B（需求单+素材上传，本文件由 WP-B 扩展引入）
---

## 现象
导入生产 ASGI 应用即崩溃：

```
File ".../ports/repositories.py", line 96, in AssetRepository
    async def get_many(self, asset_ids: Sequence[int]) -> list[AssetRecord]:
TypeError: 'function' object is not subscriptable
```

`design_hub.interface.api.asgi:app` 无法 import → 生产入口（真实 MySQL+Redis+gpt-image）起不来。
（同步 Mock 应用 `interface.api.app:app` 不受影响，因其不 import repositories.py。）

## 复现步骤
1. `cd image-code`
2. `uv run python -c "from design_hub.interface.api.asgi import app"`
3. 抛 `TypeError: 'function' object is not subscriptable`

## 期望 vs 实际
- 期望：asgi app 正常 import / 启动。
- 实际：import 阶段即 TypeError。
- 备注：`uv run mypy` 全绿 —— mypy 静态把 `list` 当内置类型，**不会**捕获这个运行时注解遮蔽问题；只有真正 import（运行类体）才暴露。

## 根因
`AssetRepository` 内定义了实例方法 `async def list(self, ...)`（line 92）。Python 类体是顺序求值的：
该方法定义完成后，名字 `list` 在**类命名空间**里被绑定为这个方法对象，遮蔽了内置 `list`。
随后 line 96 的 `get_many(...) -> list[AssetRecord]` 在类体求值期解析返回注解时，`list` 解析到的是
那个方法（function 对象）→ `function[AssetRecord]` → 不可下标 → TypeError。

为什么 `CustomerRepository`/`ProjectRepository` 的同名 `list` 方法没事：它们的 `list[...]` 注解只
出现在 `list` 方法**自身**的定义里（line 36 / 52），此时绑定尚未发生，`list` 仍是内置；只有
`AssetRepository` 同时具备「`list` 方法」+「其后另一个方法用 `list[...]` 注解」才触发。

## 建议修复（WP-B 决策，二选一）
- **方案 A（推荐，最小且彻底）**：在 `repositories.py` 顶部加 `from __future__ import annotations`。
  使全文件注解延迟为字符串、不在类体期求值，遮蔽问题消失，零 API 改动，并预防 Customer/Project 仓储
  日后踩同一坑。
- **方案 B**：把 `AssetRepository.list` 重命名为 `list_by_project`（语义也更清晰），并同步改其
  SQLAlchemy 实现与调用方。改动面比 A 大。

> 本文件归 WP-B，WP-F 不越界修改（写边界铁律）。WP-F 自身代码不 import repositories.py，已隔离
> 自检通过（5 维聚合 smoke + 路由注册均绿），仅生产 app 整体 import 被本 bug 阻断。

## 处理记录
- 2026-06-01 [开发] WP-F 集成自检时发现并根因定位，开单；状态=已确认，owner→开发(WP-B)，P1
- 2026-06-01 [开发] WP-B 后续提交已修：将 `get_many`(用 list[...] 注解) 挪到 `list` 方法**之前**，
  类体求值期 `list` 仍解析为内置 → 遮蔽不再触发（方案 A/B 之外的等价修法）。复验
  `uv run python -c "from design_hub.interface.api.asgi import app"` 已正常，ruff+mypy 全绿。
  状态→待验证，owner→QA。（注：方法顺序依赖较脆，建议 QA 顺带确认是否补 `from __future__ import annotations` 以根除同类隐患）
- 2026-06-01 [开发] WP-B 采纳**方案 A 根治**（响应上条建议，不再依赖"list 置末尾"的脆弱顺序）：
  `ports/repositories.py` + `infrastructure/db/asset_repo.py` 顶部加 `from __future__ import annotations`，
  全文件注解延迟为字符串、类体期不求值，方法名遮蔽内置类型的隐患彻底消除，零 API 改动。
  复验精确复现命令返回 FastAPI，ruff + mypy(119 文件) 全绿。状态维持**待验证**，owner=QA。
