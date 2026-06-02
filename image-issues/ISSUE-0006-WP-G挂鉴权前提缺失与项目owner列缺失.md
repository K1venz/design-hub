---
id: ISSUE-0006
title: WP-G「全量挂鉴权」受阻——鉴权能力层未实现 + project 表无 owner 列无法按本人过滤
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起 | 待确认
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发        # WP-G 挂鉴权窗口
owner: QA             # 用户定 A1+B1，已落地；阻塞 1 解除、阻塞 2 转待办，交 QA 验
created: 2026-06-01
updated: 2026-06-02
related:
  - WP: WP-G（认证授权 / 全量挂鉴权）
  - code: image-code/src/design_hub/interface/api/deps.py（现仅 EngineDep/UserIdDep）
  - code: image-code/src/design_hub/infrastructure/db/models.py（project 表无 owner 列）
---

## 背景
收到任务「WP-G 全量挂鉴权」，前提声明「WP-G 能力层(OAuth/JWT/角色/current_user/require_role)已完成，本任务只做挂载」。

## 阻塞 1：鉴权能力层在工作树中并不存在（前提与实况不符）
全树搜索（`grep -rniE "jwt|oauth|require_role|current_user|class Role|feishu|dingtalk"` over `image-code/src`）：
- 无任何 auth/JWT/OAuth 代码；无 `ports/auth.py`、无 `infrastructure/auth/*`、无 `application/auth/*`、无 `routes/auth.py`。
- 无 `Role`/角色 枚举；`interface/api/deps.py` 仅 `EngineDep` / `UserIdDep`（无 `current_user`/`require_role`）。
- `routes/admin.py` 仍留注释「鉴权待 WP-G，留 TODO」。接口清单 §2 标 WP-G「端点现全裸」、未完成。

→ 没有 `require_role`/`current_user` 依赖可挂。「挂鉴权」无法在缺能力层时进行。

## 阻塞 2：角色矩阵「项目读写仅设计师本人(按 user_id 过滤)」无数据支撑
- `project` 表列为 `customer_id/name/status/current_round`，**无 owner/user_id 归属列**；`customer` 同样无归属。
- 仅 `generation_job` 有 `user_id`（出图人）。无项目归属字段 → 无法按"本人"过滤项目。
- 加 `project.owner_user_id` = DB schema 变更，触发「DB 改动先问用户」硬规则，需用户确认，且与本任务「不改 schema」约束冲突。

## 需要拍板（二选一/组合）
**方向 A（能力层）**：
- A1（推荐）：开发先建**最小能力层**——`uv add pyjwt` + Role 枚举(设计师/管理者) + `current_user`/`require_role` 依赖 + **mock** OAuth 回调(`/auth/{provider}/callback` 发 dev token)+`/me`；dev JWT 密钥走 `.env`（默认占位、不入库）。真实飞书/钉钉 OAuth 待用户给 app 凭据。建好后全量挂鉴权。
- A2：暂停，等并行 WP-G 能力层 agent 把能力层提交到 HEAD 后再挂。
- A3：用户现在提供飞书/钉钉 `app_id/secret`（入 `.env`），开发建真实 OAuth 全链路。

**方向 B（项目按人过滤）**：
- B1（推荐）：先只做**角色级门禁**（全端点需登录；`/admin`·`/dashboard` 仅管理者；`/generate` 设计师+管理者）；"设计师只见本人项目"因缺 owner 列**暂缓**，待加列后再做。
- B2：加 `project.owner_user_id` 列 + Alembic 迁移（需用户确认动 schema），项目建/查带 owner、按 owner 过滤。
- B3：不做本人过滤（登录设计师可读写所有项目）。

## 处理记录
- 2026-06-01 [开发] WP-G 挂鉴权侦察发现能力层缺失 + project 无 owner 列；AskUserQuestion 被 don't-ask 模式拒绝，无法交互澄清。按规则不擅自建 2.5 人天能力层/不擅自动 schema，开单上报，owner→PM/用户。状态=待确认。
- 2026-06-02 [开发] 用户确认方向 **A1 + B1**，已落地：
  - **阻塞 1 解除**：建最小鉴权能力层(pyjwt JWT+Role+current_user/require_role+mock OAuth 回调+/me)，
    并在 asgi include 级全量挂角色矩阵(/auth 公开;业务端点需登录;dashboard·admin 仅管理者)。
    提交 9ba7d1d/17553c4/393bde2，ruff+mypy(160)+HTTP 全矩阵 smoke 绿。
  - **阻塞 2 转待办(非阻塞)**：B1 只做角色级门禁；"设计师只见本人项目"因 project 无 owner 列**暂缓**，
    待加 `project.owner_user_id` 列(需用户批准动 schema)再做。
  - **遗留待办**(需用户/凭据)：① 真实飞书/钉钉 OAuth(替换 MockOAuthClient，需 app_id/secret 入 .env)；
    ② project owner 列 + 按本人过滤。状态→待验证，owner→QA。
