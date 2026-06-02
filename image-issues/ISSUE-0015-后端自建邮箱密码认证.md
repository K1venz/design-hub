---
id: ISSUE-0015
title: 后端：自建邮箱密码 注册/登录 + 用户管理 + 移除 OAuth（app_user 表）
status: 待验证
severity: P1
reporter: 前端
owner: QA             # 后端已实现+sqlite 验证；真实库迁移 apply + .env seed 后 QA 复验
created: 2026-06-02
updated: 2026-06-02
related:
  - spec: docs/superpowers/specs/2026-06-02-自建邮箱密码认证-design.md
  - code: image-code/src/design_hub/application/auth/ · infrastructure/auth/ · interface/api/routes/auth.py
---

## 诉求
按 spec 实现自建邮箱密码认证，替换 OAuth/mock。前端不碰 image-code，开此条指给开发。

## ⚠️ 涉及数据库（按规矩先确认）
新建表 `app_user`(id / email UNIQUE / password_hash bcrypt / name / role 默认设计师 / created_at) + Alembic 迁移。
**用户已确认建此表**；实施前请再与用户核连接/迁移环境。

## 实现清单
1. ORM `AppUser` + 迁移；`ports/user_repository.py` + `infrastructure/db/user_repo.py`（get_by_email/get_by_id/add/set_role/list）。
2. `infrastructure/auth/password.py`：bcrypt（`uv add bcrypt`，CLI 装，勿手改 pyproject）。
3. `application/auth/account_service.py`：register（重复邮箱→DomainError 409 / 密码<8→ValueError 400 / 默认设计师 / 签 JWT）、login（失败→AuthenticationError 401，统一文案）、seed_admin（幂等）。
4. `application/admin/user_admin_service.py`：list_users / set_role（"最后一个管理者不可降级"→409）。
5. 端点：`POST /auth/register`、`POST /auth/login`（公开）；`GET /admin/users`、`PUT /admin/users/{id}/role`（仅管理者，挂 require_role）。`GET /me` 不变。
6. `Settings` 增 `seed_admin_email`/`seed_admin_password`（SecretStr，空=不 seed，走 .env）；asgi lifespan 启动 seed。
7. **移除**：`/auth/{provider}/callback`、`mock_oauth.py`、`ports/auth.py::OAuthClient`、`auth_service.py` 的 dept→role 映射；asgi 把 `AuthService(oauth=...)` 换 `AccountService`。
8. 复用：`PyJwtTokenService`/`Role`/`AuthUser`/deps/边界映射。`AuthUser.user_id=str(app_user.id)`，dept=None；`MeResponse` 可选加 email。

## 契约（供前端并行）
- `POST /auth/register {email,password,name}` → `{jwt,role,name}`（复用 LoginResponse）
- `POST /auth/login {email,password}` → `{jwt,role,name}`
- `GET /admin/users` → `{id,email,name,role,created_at}[]`
- `PUT /admin/users/{id}/role {role}` → 用户对象

## QA 验证步骤（开发建议）
**前置（运维/起服务前）**：① `.env` 配真实 `DB_URL`(MySQL image_gen)；② 对真实库跑
`uv run alembic upgrade head`(建 app_user 表)；③ `.env` 配 `SEED_ADMIN_EMAIL`/`SEED_ADMIN_PASSWORD`
(否则无初始管理者)。起 asgi 后 lifespan 会幂等 seed 管理员。
**用例（零成本，不出图）**：
1. `POST /auth/register {email,password(≥8),name}` → 200 `{jwt,role=设计师,name}`；带该 jwt `GET /me` 通。
2. 重复邮箱注册 → 409；密码 <8 → 400；邮箱格式非法 → 400(pydantic)。
3. `POST /auth/login` 对密码 → 200；错密码/不存在邮箱 → 401(统一文案"邮箱或密码错误")。
4. seed 管理员登录 → `GET /admin/users` 列用户；设计师 token 打 `/admin/users` → 403。
5. `PUT /admin/users/{设计师id}/role {role:管理者}` 提升 → 该用户**重登**拿管理者导航；
   降级最后一个管理者 → 409；改不存在用户 → 404。
6. 确认旧 `/auth/{provider}/callback` 已 404(OAuth 移除)。

## 处理记录
- 2026-06-02 [前端] 按已确认 spec 开条目指给开发；DB 表需开发实施前与用户再核，owner=开发。
- 2026-06-02 [开发] **已实现**(commit 4213541)：按 spec 落地，NO 向后兼容移除 OAuth/mock。
  新增 PasswordHasher(bcrypt)/UserRepository(AppUser ORM)/AccountService(register 默认设计师·
  重复 409·弱密码 400·login 401 统一文案·seed_admin 幂等)/UserAdminService(list·set_role 最后管理者
  不可降 409)/路由 register·login·me·admin users/EmailStr(email-validator)。app_user 表 + 迁移
  4a2a261611d9(链 f12587232511)。移除 mock_oauth/auth_service/OAuthClient/OAuthProfile/callback。
  验证 ruff+mypy(170)+sqlite smoke 全链路 + 迁移 upgrade/downgrade round-trip 干净。
  **DB 确认**：表已用户确认；**生产 MySQL 的 alembic upgrade head 尚未执行**(`.env` 缺 DB_URL，
  无 MySQL 凭据)——这是 QA 复验的前置(同 0007/0010 的 .env 缺口)，需 Ops 配 DB_URL 后 apply。
  状态→待验证，owner→QA。
  > 前端契约已就绪(§契约/spec §5)，前端三页(注册/登录改造/用户管理)可并行。
