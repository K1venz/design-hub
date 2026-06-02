# image-web · 设计中台前端

设计师 AI 副驾驶中台的 Web 前端。独立项目，与 `image-code`（后端 `design_hub`）同级，
经 **dev proxy** 消费后端 26 个端点的契约。**不碰后端代码**；需后端改动 → 去 `image-issues` 开条目。

> 当前进度：**FE-0 完成** —— 脚手架 + 类型化契约客户端 + 登录 + 应用骨架（按角色导航 + 401 跳登录）。
> 业务页面 FE-1~7 拆分见 `../docs/前端工作包拆分.md`。

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
# 在 image-code/ 下，真实基础设施（MySQL+Redis+.env 配 GPT_IMAGE_*）：
uv run uvicorn design_hub.interface.api.asgi:app --port 8000
# 或零基础设施快速验证（临时 sqlite + 无认证 redis）：
#   DB_URL=sqlite+aiosqlite:////tmp/dh.db uv run alembic upgrade head
#   redis-server --port 6380 &
#   DB_URL=sqlite+aiosqlite:////tmp/dh.db REDIS_URL=redis://127.0.0.1:6380/0 \
#     uv run uvicorn design_hub.interface.api.asgi:app --port 8000
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
# 1) 从后端导出最新 openapi.json（离线构造 app，无需真 DB/Redis）：
cd ../image-code && uv run python -c "import json;from design_hub.interface.api.asgi import create_production_app;print(json.dumps(create_production_app().openapi(),ensure_ascii=False,indent=2))" > ../image-web/openapi.json
# 2) 重新生成类型：
cd ../image-web && npm run gen:api
```

`src/api/client.ts` 用 `openapi-fetch` 封装类型化客户端：统一注入 `Bearer`、401 清会话并广播跳登录。

## 目录结构

```
src/
  api/         schema.d.ts(生成) · client.ts(openapi-fetch+中间件) · auth.ts(hooks) · query-client.ts · errors.ts
  stores/      auth-store.ts(Zustand persist: token→localStorage)
  routes/      ProtectedRoute(鉴权闸门+/me引导) · RoleRoute(角色闸门→403)
  components/   ui/(shadcn) · layout/(AppLayout 按角色导航) · brand/ · feedback/ · PagePlaceholder
  pages/       Login · Workbench · Dashboard(管理者) · AdminModels(管理者) · Forbidden(403) · NotFound(404)
  App.tsx      Providers(Query/Tooltip/Router/Toaster) + 路由 + 401 监听
```

## 设计系统（FE-0 定调，FE-1~7 复用）

「工作室控制台」方向：暖纸感浅底 + 青墨主色 + 琥珀高光，中性低彩度 chrome 不与电商成品图配色打架。
令牌集中在 `src/index.css`（oklch + `@theme`，含 dashboard 图表色板）。
字体：Hanken Grotesk(UI 拉丁) + PingFang(中文) / Fraunces(展示) / JetBrains Mono(数字 ID)。

## 登录（mock OAuth）

后端 `POST /auth/{provider}/callback` 当前是 mock：按 `code` 前缀映射角色
（`mgr-*`→管理者、`out-*`→403、其余→设计师）。前端登录页**开发态**提供「设计师/管理者」
身份切换以验证按角色导航；生产态隐藏（真实飞书/钉钉 OAuth 待后端接凭据）。

## 依赖说明

- **`legacy-peer-deps`**：`openapi-typescript@7` 的 peer 仍是 `typescript@^5.x`，与本项目最新 TS6 冲突
  （生成的 `.d.ts` 在 TS6 下正常编译）。安装时请加 `--legacy-peer-deps`，或设环境变量
  `NPM_CONFIG_LEGACY_PEER_DEPS=true`。待 openapi-typescript 放宽 peer 后移除。
  （本仓策略未落 `.npmrc`——如需团队统一，可由有权限者加 `legacy-peer-deps=true`。）
- 依赖一律用 CLI（`npm install <pkg>`）增删，勿手改 `package.json` 版本。

## 已知事项（移交 FE-1~7）

- **SSE + JWT（FE-3）**：原生 `EventSource` 无法设自定义请求头，而 `GET /generate/{job_id}/events`
  需 `Authorization: Bearer`。需后端支持 query 传 token（或改用 fetch-stream）——见 `image-issues`。
