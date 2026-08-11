# image-web · 设计中台前端

设计师 AI 副驾驶中台的 Web 前端。独立项目，与 `image-code`（后端 `design_hub`）同级，
经 **dev proxy** 消费后端 26 个端点的契约。**不碰后端代码**；需后端改动 → 去 `image-issues` 开条目。

> 当前进度：**listing 一键出图工作台全链路落地** —— 两步上传 → 纯 prompt 直出 → SSE 逐张到达 → 历史/详情；
> 登录走自建邮箱密码（注册/登录）；管理页（仪表盘 / 模型 / 用户 / 客户）统一顶栏导航。
> 出图工作台 v2 设计见 `docs/出图工作台-v2-商品套图重做-设计.md`。

## 技术栈（PRD §6.1）

Vite 8 · React 19 · TypeScript 6 · Tailwind v4 · shadcn/ui(radix) · TanStack Query v5 ·
Zustand v5 · React Router v7 · recharts · 原生 EventSource（SSE，FE-3 用）。

## 起步

```bash
nvm use                 # 读 .nvmrc（Node 22；本机若无 nvm，用已装的 Node ≥20 亦可）
npm install             # 见下「依赖说明」
npm run dev             # http://localhost:3000
```

需要**同时跑后端**（dev proxy 把 /api 转给它）：

```bash
# 在 image-code/ 下（异步出图 / SSE 走单进程，无 Redis）：
#   首次空库先建表： uv run alembic upgrade head      （默认本机 sqlite design_hub.db）
uv run uvicorn design_hub.interface.api.asgi:app --port 8000
#   真实出图需 .env 配 GPT_IMAGE_*（presence-based：配了就真出图、不配启动即崩）
#   起法 / 凭据以 image-code 为准
```

## 脚本

| 命令 | 作用 |
|---|---|
| `npm run dev` | Vite dev（端口 3000，/api → 127.0.0.1:8000，剥 `/api` 前缀） |
| `npm run build` | `tsc -b && vite build`（类型检查 + 生产构建） |
| `npm run typecheck` | `tsc -b` 仅类型检查 |
| `npm run lint` | ESLint |
| `npm run gen:api` | 由 `openapi.json` 生成 `src/api/schema.d.ts`（唯一契约源） |

## 契约客户端（单一事实源）

`src/api/schema.d.ts` 由后端 OpenAPI 生成，**勿手改**。更新流程：

```bash
# 1) 从后端导出最新 openapi.json（离线构造 app，无需真 DB/Redis），再字节复制到前端：
cd ../image-code && uv run python -c "import json;from design_hub.interface.api.asgi import create_production_app;print(json.dumps(create_production_app().openapi(),ensure_ascii=False,indent=2))" > openapi.json
cp openapi.json ../image-web/openapi.json
# 2) 重新生成类型并检查两份契约一致：
cd ../image-web && npm run gen:api
cmp ../image-code/openapi.json openapi.json
```

`src/api/client.ts` 用 `openapi-fetch` 封装类型化客户端：统一注入 `Bearer`、401 清会话并广播跳登录。

## 目录结构

```
src/
  api/         schema.d.ts(生成) · client.ts(openapi-fetch+中间件) · auth.ts(hooks) · query-client.ts · errors.ts
  stores/      auth-store.ts(Zustand persist: token→localStorage)
  routes/      ProtectedRoute(鉴权闸门+/me引导) · RoleRoute(角色闸门→403)
  components/   ui/(shadcn) · layout/(顶栏导航壳) · listing/(上传/配置/画廊/rail) · visual/(配饰) · dashboard/ · brand/ · feedback/
  pages/       Login/Register · Workbench(listing 两栏出图) · History/HistoryDetail · Customers ·
               Dashboard·AdminModels·AdminUsers(管理者) · Forbidden(403) · NotFound(404)
  App.tsx      Providers(Query/Tooltip/Router/Toaster) + 路由 + 401 监听
```

## 设计系统（FE-0 定调，FE-1~7 复用）

「工作室控制台」方向：暖纸感浅底 + 青墨主色 + 琥珀高光，中性低彩度 chrome 不与电商成品图配色打架。
令牌集中在 `src/index.css`（oklch + `@theme`，含 dashboard 图表色板）。
字体：Hanken Grotesk(UI 拉丁) + PingFang(中文) / Fraunces(展示) / JetBrains Mono(数字 ID)。

## 登录（自建邮箱密码）

后端 `POST /auth/register` 接收邮箱、密码（至少 8 位）和姓名，只返回
`{message, challenge_id}`，不会登录；`POST /auth/register/verify` 必须提交邮箱、
不可猜的 challenge ID 与 6 位验证码，成功才返回登录会话；resend 同样绑定旧 ID，
并返回需要替换的新 ID。注册页只在组件内存保存 `{email, challengeId}`，密码、验证码
和 challenge 均不进入持久化存储。`POST /auth/login` 供已验证账号登录，只有成功会话的
token 持久化到 localStorage。
SSE 鉴权走 query `?access_token=<jwt>`（原生 EventSource 不能带头，见 [ISSUE-0011]）。
（原 mock OAuth code-前缀映射已废弃；真实飞书/钉钉 OAuth 待后端接凭据，见 [ISSUE-0013]。）

## 依赖说明

- **`legacy-peer-deps`**：`openapi-typescript@7` 的 peer 仍是 `typescript@^5.x`，与本项目最新 TS6 冲突
  （生成的 `.d.ts` 在 TS6 下正常编译）。安装时请加 `--legacy-peer-deps`，或设环境变量
  `NPM_CONFIG_LEGACY_PEER_DEPS=true`。待 openapi-typescript 放宽 peer 后移除。
  （本仓策略未落 `.npmrc`——如需团队统一，可由有权限者加 `legacy-peer-deps=true`。）
- 依赖一律用 CLI（`npm install <pkg>`）增删，勿手改 `package.json` 版本。

## 已知事项

- **SSE + JWT** ✅：原生 `EventSource` 不能带请求头 → 已改 query 鉴权 `?access_token=<jwt>`（后端已支持，[ISSUE-0011]）。
- listing 历史已持久化（后端落 DB + 前端历史/详情页，[ISSUE-0030]）；图 url 读时签名现签（[ISSUE-0029] / 火山 TOS）。
