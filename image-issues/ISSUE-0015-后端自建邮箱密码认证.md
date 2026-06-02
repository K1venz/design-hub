---
id: ISSUE-0015
title: 后端：自建邮箱密码 注册/登录 + 用户管理 + 移除 OAuth（app_user 表）
status: 待确认
severity: P1
reporter: 前端
owner: 开发
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

## 处理记录
- 2026-06-02 [前端] 按已确认 spec 开条目指给开发；DB 表需开发实施前与用户再核，owner=开发。
