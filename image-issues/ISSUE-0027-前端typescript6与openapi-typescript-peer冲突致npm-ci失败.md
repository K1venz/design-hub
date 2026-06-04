---
id: ISSUE-0027
title: 前端 typescript 6 与 openapi-typescript peer 冲突，npm ci 失败（CI 构建挂）
status: 待确认
severity: P2
reporter: 运维
owner: 前端
created: 2026-06-04
updated: 2026-06-04
related:
  - code: image-web/package.json
  - ci: .github/workflows/deploy.yml
---

## 现象
CI（方案A 自动部署）在「Build frontend」步骤 `npm ci` 失败：
```
npm error ERESOLVE could not resolve
npm error While resolving: openapi-typescript@7.13.0
npm error Found: typescript@6.0.3
npm error peer typescript@"^5.x" from openapi-typescript@7.13.0
npm error Conflicting peer dependency: typescript@5.9.3
```

## 根因
`image-web/package.json`：`typescript@~6.0.2`（6.x）与 `openapi-typescript@^7.13.0`（peer 要 `typescript@^5.x`）版本冲突。
本地能 build 是因为开发机历史上用 `--legacy-peer-deps`/`--force` 生成过 lockfile；仓库里**没有提交 `.npmrc`**，干净 CI 环境 `npm ci` 直接 ERESOLVE。

## 期望 vs 实际
- 期望：`npm ci` 在干净环境直接成功
- 实际：peer 冲突报错，CI 构建失败

## 建议修复（前端执行；运维不改 image-web）
任选其一，干净落到前端域：
1. 提交 `image-web/.npmrc`，内容 `legacy-peer-deps=true`（最简；本地/CI 行为一致）
2. 或在 package.json 加 `overrides` 固定 typescript，给 openapi-typescript 放行
3. 或把 typescript 降到 5.x（若 6.x 非必需），或升级/替换 openapi-typescript 到支持 ts6 的版本

## 运维侧临时处置
CI workflow 已临时用 `npm ci --legacy-peer-deps` 解开（.github/workflows/deploy.yml）。
前端按上面任一方式落地后，本 flag 可去掉。

## 处理记录
- 2026-06-04 [运维] CI 首跑暴露，创建本条；workflow 临时加 --legacy-peer-deps 不阻塞部署，状态=待确认，owner=前端
