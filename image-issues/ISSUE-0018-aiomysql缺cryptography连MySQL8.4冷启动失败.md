---
id: ISSUE-0018
title: aiomysql 缺 cryptography，连 MySQL 8.4(caching_sha2_password) 冷启动会失败
status: 已确认
severity: P1
reporter: 运维
owner: 开发
created: 2026-06-03
updated: 2026-06-03
related:
  - code: image-code/pyproject.toml
  - code: image-code/src/design_hub/config/settings.py
  - PRD: §6.4
---

## 现象
生产 MySQL 为 8.4.9，root 账户认证插件为 `caching_sha2_password`，且 `mysql_native_password` 已 DISABLED。
应用依赖 `aiomysql`（基于 PyMySQL），但 `pyproject.toml` / `uv.lock` 中**没有 `cryptography`**。
明文 TCP 连接下，`caching_sha2_password` 的「完整认证」需用服务器 RSA 公钥加密口令 → 必须 `cryptography`。
缺 `cryptography` 时只有「快速认证」(SHA256 scramble，标准库可算) 可走，而快速认证依赖**服务端口令缓存命中**。

## 复现步骤
1. 重启 MySQL 容器（清空 caching_sha2_password 缓存）
2. 应用 (api 容器，无 cryptography) 冷启动首次连库
3. 首次认证 = 缓存未命中 = 完整认证 = 明文 TCP 下需 cryptography → 抛错连不上

## 期望 vs 实际
- 期望：应用对 MySQL 8.4 的连接稳定，MySQL 重启后冷启动也能直接连上
- 实际：缓存热时能连（运维实测 `CONNECT_OK_WITHOUT_CRYPTOGRAPHY`），但 MySQL 重启后缓存清空，冷启动首连会因缺 cryptography 失败

## 环境 / 上下文
- 服务器 14.103.51.191 Ubuntu 24.04 / MySQL 8.4.9 (docker `mysql:8.4`)
- 运维实测：临时容器装 aiomysql（不装 cryptography）连库成功——因 MySQL 已运行、root 缓存热；装 cryptography 后同样成功
- 部署决策 ②B：应用用 root 连库
- 当前部署靠「缓存热」勉强可跑，但不健壮

## 建议修复（开发执行；运维不改业务代码）
- `uv add cryptography`（属网络/IO 依赖正当性，取最新版）
- 这是连标准 MySQL 8.4 的**必需依赖**，非临时补丁，不算「兼容层」
- 修复后运维侧无需改动（镜像重建即生效）

## 处理记录
- 2026-06-03 [运维] 部署联调中实测确认，创建本条，状态=已确认，owner=开发
