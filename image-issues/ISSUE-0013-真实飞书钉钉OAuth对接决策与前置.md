---
id: ISSUE-0013
title: 真实飞书/钉钉 OAuth 对接 —— 决策与前置（凭据 + 部门角色方案）
status: 挂起
severity: P2
reporter: 前端
owner: PM
created: 2026-06-02
updated: 2026-06-02
related:
  - 调研: image-web/docs/oauth-飞书钉钉登录调研.md
  - code: image-code/src/design_hub/ports/auth.py (OAuthClient 端口)
  - code: image-code/src/design_hub/infrastructure/auth/mock_oauth.py (待替换)
  - 前端: image-web/src/pages/LoginPage.tsx (待改跳授权)
---

## 现象 / 诉求
用户希望把当前 **mock 登录** 换成真实**飞书 / 钉钉 OAuth**。已完成调研（见 `image-web/docs/oauth-飞书钉钉登录调研.md`）。
技术可行，后端 `OAuthClient` 端口早已为此预留（换实现即可，LSP）。但开工前需先解决三个**非代码前置**。

## 待用户/PM 决策的前置（球在这里）
1. **提供应用凭据**（用户）：在飞书/钉钉开放平台注册自建应用，给出
   - 飞书：App ID + App Secret；
   - 钉钉：AppKey + AppSecret；
   - 并配置回调 redirect_uri（本地联调需一个可达地址，纯 localhost 可能不被接受 → 需内网穿透或部署域名）。
2. **定部门→角色方案**（PM/用户，影响权限门槛）：
   - **方案 A**：照 PRD §6.3.3 解析部门名映射角色 → 需「通讯录/组织架构读」权限 + **企业管理员审批**，且依赖部门名精确匹配（脆弱）、每次登录多 2~3 次 API。
   - **方案 B（前端建议）**：OAuth 只取基础身份，角色由**应用内**配置/管理者分配（解耦部门名、OAuth 权限轻、易审批）。需一个角色管理后台 + bootstrap 首个管理者。
3. **权限审批**（企业管理员）：按所选方案申请并审批应用权限。

## 决策后的实施（不阻塞可先排期）
- **后端**（owner→开发）：`FeishuOAuthClient`/`DingTalkOAuthClient` 实现 `OAuthClient`（httpx）+ provider 路由分流 + 凭据走 .env + asgi 装配替换 mock；（方案 B）角色映射表/管理端点；可选 `GET /auth/{provider}/authorize-url`。
- **前端**（owner→前端）：登录页改"跳授权页" + 新增 `/auth/callback` 路由（读 code/state→`POST /auth/{provider}/callback`换 JWT）。改动小，现有 store/守卫复用。

## 影响
- 现 mock 登录可继续支撑前端开发与演示；真实 OAuth 待上面前置齐备。
- 与 WP-G「真实飞书/钉钉 OAuth 待凭据」一致（见 ISSUE-0006 待办项）。

## 用户决策（2026-06-02）
- **不需要获取部门** → 采纳**方案 B**：OAuth 只认证拿身份，角色应用内决定。
  - 影响：去掉通讯录调用、组织架构读权限、管理员重审批 → 对接大幅简化。
  - 后端改动收敛为：2 个身份适配器（换 token + user_info）+ `AuthService` 角色判定改「白名单/默认」+ provider 分流 + 凭据进 .env + asgi 替换 mock。**无 DB 改动**（管理者走 .env 白名单）。估编码 ~0.5–1 人天。
  - 费用确认：两家登录/身份接口对自建应用**免费**（钉钉通讯录/免登不计月额度；飞书有每日调用量上限，登录低频无碍）。
- **仍待用户定**：① 应用凭据（App ID/Secret、AppKey/Secret）+ 可达 redirect_uri；② 没部门时设计师/管理者如何区分（建议默认设计师 + `.env` `MANAGER_USER_IDS` 白名单）。

## 处理记录
- 2026-06-02 [前端] 完成调研并落 `image-web/docs/oauth-飞书钉钉登录调研.md`；开本条上报决策前置，owner=PM（方案 A/B + 凭据），状态=挂起待用户输入。
- 2026-06-02 [前端] 用户拍板「不需要部门」→ 锁定方案 B，重估后端工作量为小（~0.5–1 人天，无 DB 改动）；费用确认登录免费。待用户给凭据 + 定角色区分方式后即可实施。
