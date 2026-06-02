# 飞书 / 钉钉 真实 OAuth 登录 · 调研

> 目的：评估把当前 mock 登录替换为真实飞书/钉钉 OAuth 的可行性、流程、前置条件与工作量。
> 结论：**技术可行，后端抽象已就绪**（`OAuthClient` 端口，换实现即可，LSP）。但有现实前置（注册应用 + 凭据 + 管理员审批权限）与一个**部门→角色映射**的设计难点需先定。
> 日期：2026-06-02。调研者：前端。
>
> **用户已决策（2026-06-02）**：**不需要获取部门** → 采纳 §3 **方案 B**（OAuth 只认证、角色应用内决定）。
> 据此后端改动收敛为「身份适配器 + 角色按白名单/默认」，**无需通讯录/组织架构读权限、无 DB 改动**，估编码 ~0.5–1 人天。
> 费用：两家登录/身份接口对自建应用**免费**（详见 §4 补充）。仍待：应用凭据 + 可达 redirect_uri + 角色区分方式。详见 `image-issues/ISSUE-0013`。

---

## 0. 现状与契约（已就绪部分）

后端 `application/auth/auth_service.py` 的登录用例已是标准 OAuth 形状：

```
POST /auth/{provider}/callback  body {code}  → {jwt, role, name}
login(code): oauth.exchange(code) → OAuthProfile{user_id, name, dept} → role_for_dept(dept) → 签 JWT
```

- `ports/auth.py::OAuthClient.exchange(code) -> OAuthProfile{user_id, name, dept}` 是唯一要替换的端口。
- 当前 `MockOAuthClient` 按 code 前缀造部门。真实化 = 新增 `FeishuOAuthClient` / `DingTalkOAuthClient` 实现该端口，asgi 装配处替换（DIP/LSP，**不动用例与路由**）。
- **关键**：`exchange` 必须产出**部门名 `dept`**（设计部/管理层/负责人），`role_for_dept` 才能映射。这是整个集成最难的一环（见 §3）。

**前端契约也已就位**：`POST /auth/{provider}/callback {code}` 正是 OAuth 回调换 JWT 的标准形状——前端只需把"发占位 code"改成"走真实授权拿真 code"。

---

## 1. 飞书（Lark）OAuth 流程

1. **前端跳授权页**：
   `https://accounts.feishu.cn/open-apis/authen/v1/authorize?client_id={App ID}&redirect_uri={回调URL}&scope={权限空格分隔}&state={CSRF}`
2. 用户同意 → 飞书 302 回 `redirect_uri?code={authorization_code}&state=...`（code 5 分钟有效、一次性）。
3. **后端换 token**：`POST https://open.feishu.cn/open-apis/authen/v2/oauth/token`
   body `{grant_type:"authorization_code", client_id, client_secret, code, redirect_uri}` → `access_token`(user_access_token)。
4. **后端拿身份**：`GET https://open.feishu.cn/open-apis/authen/v1/user_info` 头 `Authorization: Bearer {access_token}`
   → `{name, open_id, union_id, user_id, ...}`。**⚠️ 不含部门**。
5. **后端解析部门**（难点）：`GET https://open.feishu.cn/open-apis/contact/v3/users/{user_id}` → `department_ids[]`（是部门 **ID**，非名）；再 `GET /open-apis/contact/v3/departments/{dept_id}` 拿部门**名**。
   - 需权限「获取用户组织架构信息」+「以应用/用户身份读取通讯录」，且**部门路径字段需 user_access_token 调用**。

**凭据**：飞书开放平台「自建应用」→ App ID + App Secret。

---

## 2. 钉钉（DingTalk）OAuth 流程（新版 v1.0）

1. **前端跳授权页**：
   `https://login.dingtalk.com/oauth2/auth?redirect_uri={回调URL}&response_type=code&client_id={AppKey}&scope=openid&state={CSRF}&prompt=consent`
2. 用户扫码/同意 → 回 `redirect_uri?authCode={code}&state=...`。
3. **后端换 token**：`POST https://api.dingtalk.com/v1.0/oauth2/userAccessToken`
   body `{clientId, clientSecret, code, grantType:"authorization_code"}` → `accessToken`。
4. **后端拿身份**：`GET https://api.dingtalk.com/v1.0/contact/users/me` 头 `x-acs-dingtalk-access-token: {accessToken}`
   → `{nick(姓名), openId, unionId, ...}`。**⚠️ 不含部门**。
5. **后端解析部门**（难点）：需企业内部应用 access_token（AppKey/AppSecret 换）+ 由 unionId 反查 userid（`/topapi/user/getbyunionid`）→ `/topapi/v2/user/get` 拿 `dept_id_list` → `/topapi/v2/department/get` 拿部门名。需「通讯录个人信息读权限」等。

**凭据**：钉钉开放平台「扫码登录应用 / 企业内部应用」→ AppKey + AppSecret。

---

## 3. 难点：部门 → 角色映射（必须先定方案）

两家的「登录用户信息」**都只给身份（姓名/ID），不给部门**。要拿部门名 → 角色，必须**额外调通讯录 API + 申请组织架构读权限**（须**企业管理员在后台审批**），且：

- 返回的是部门 **ID**，要再调一次才拿到**名**；
- 角色映射依赖部门**名精确等于** `设计部/管理层/负责人`——组织实际命名不同就崩。

**建议（择一，影响 OAuth 权限范围大小）：**

- **方案 A（照搬 PRD §6.3.3）**：解析部门名映射角色。权限重（要组织架构读权限+管理员审批）、脆弱（依赖部门名字符串）、每次登录多 2~3 次 API。
- **方案 B（推荐，解耦）**：OAuth **只取基础身份**（姓名+ID，权限轻、易审批），角色由**应用内**决定——
  - 维护 `user_id/部门ID → role` 配置表（管理者在后台分配，复用 WP-H 那套 admin 模式），或首登默认设计师、由管理者提升；
  - 好处：OAuth 不需要组织架构读权限（审批门槛大降）、不依赖部门名、可控。
  - 代价：需一个「角色管理」后台 + 首个管理者的引导（环境变量指定 bootstrap 管理者 user_id）。

> 方案 B 把「OAuth 只管认证、角色由系统授权」分离，更干净，也大幅降低对接难度。**需 PM/用户拍板。**

---

## 4. 现实前置（必须用户/管理员提供，代码无法替代）

1. 在飞书 / 钉钉**开放平台注册自建应用**，拿 **App ID/Secret**（飞书）、**AppKey/Secret**（钉钉）。
2. 配置**回调 redirect_uri**：须真实可达。飞书/钉钉一般要求**已登记的域名**；本地开发需登记 `http://localhost:3000/...`（部分允许）或用内网穿透（ngrok/cpolar）。**纯 localhost 可能不被接受**——这是本地联调的主要障碍。
3. **申请权限并经企业管理员审批**：方案 A 需通讯录/组织架构读权限；方案 B 仅需基础身份。
4. 应用需在企业内**发布/授权**给目标用户。

---

## 5. 工作量拆分

**后端（image-code，owner=开发，主要工作）**：
- 新增 `infrastructure/auth/feishu_oauth.py` / `dingtalk_oauth.py` 实现 `OAuthClient`（httpx，I/O 可重试）；
- `provider` 路由分流（当前 mock 不分流，真实需按 `{provider}` 选适配器）；
- 凭据走 `.env`（FEISHU_APP_ID/SECRET、DINGTALK_APP_KEY/SECRET），asgi 装配处按 provider 注册；
- （方案 B）角色映射表 + 角色管理端点；
- 可选：`GET /auth/{provider}/authorize-url` 返回授权跳转 URL（把 client_id/scope 收在服务端）。

**前端（image-web，owner=前端=我）**：
- 登录页「飞书/钉钉登录」从"发占位 code"改为**跳授权页**（用上面的 authorize URL）；
- 新增回调路由 `/auth/callback`：读 URL 的 `code/authCode` + `state` 校验 → `POST /auth/{provider}/callback` 拿 JWT → 存 → 进工作台；
- 复用现有 store/守卫，改动小。
- 依赖：从后端 `authorize-url` 端点或 Vite env 取 client_id/scope。

**对接顺序**：用户给凭据 + 选方案(A/B) → 后端实现适配器 + (B)角色表 → 前端改登录跳转 + 回调路由 → 用真实账号端到端联调（需可达 redirect_uri）。

---

## 6. 一句话结论

可行，且后端架构早已为此预留（换 `OAuthClient` 实现即可）。**真正的门槛不是代码，而是：① 注册应用拿凭据；② 部门→角色怎么定（建议方案 B 解耦，省掉重权限）；③ 本地联调要一个可达的 redirect_uri。** 这三件定了，前后端各自的改动都不大。

## 参考
- 飞书 获取 user_access_token：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/authentication-management/access-token/get-user-access-token
- 飞书 获取登录用户信息 user_info：https://open.feishu.cn/document/server-docs/authentication-management/login-state-management/get
- 飞书 通讯录 v3 获取单个用户（department_ids）：https://open.feishu.cn/document/server-docs/contact-v3/user/get
- 钉钉 OAuth2.0 / 获取用户 token：https://open.dingtalk.com/document/development/obtain-user-token
- 钉钉 扫码登录第三方网站：https://open.dingtalk.com/document/orgapp/scan-qr-code-to-log-on-to-third-party-websites
