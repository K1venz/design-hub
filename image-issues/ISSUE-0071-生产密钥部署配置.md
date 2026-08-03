---
id: ISSUE-0071
title: 生产密钥部署配置
status: 已确认
severity: P1
reporter: 开发
owner: 运维
created: 2026-07-30
updated: 2026-08-03
related:
  - code: image-code/src/design_hub/config/settings.py
  - code: image-code/src/design_hub/composition.py
  - Task 2: Generalize RSA Secret Encryption
---

## 现象

生产部署环境模板尚未声明 RSA 密钥持久化的强制配置。

## 复现步骤

1. 使用 `image-ops/deploy/.env.example` 准备生产部署环境。
2. 未设置 `REQUIRE_PERSISTENT_SECRET_CIPHER=true` 和持久 RSA 私钥。
3. 部署无法保证 API 与 Worker 使用同一把持久密钥。

## 期望 vs 实际

- 期望：生产部署明确设置 `REQUIRE_PERSISTENT_SECRET_CIPHER=true`，并为 API 与 Worker 提供同一份持久 `AUTH_RSA_PRIVATE_KEY_PEM`。
- 实际：部署模板缺少上述配置说明。

## 环境 / 上下文

Task 2 将 RSA-OAEP 密钥从密码传输专用组件泛化为应用敏感信息加密组件。生产环境缺失持久私钥会使已加密数据无法在进程重启后解密。

## 处理记录

- 2026-07-30 [开发] 创建，状态=已确认，关联 Task 2，owner=运维。
- 2026-08-03 [开发] 收口核对：生产 API/Worker 已使用同一持久 RSA 密钥并通过重启后的动态模型读取；但 `image-ops/deploy/.env.example` 仍未声明 `REQUIRE_PERSISTENT_SECRET_CIPHER=true` 与持久 `AUTH_RSA_PRIVATE_KEY_PEM` 注入方式。该单保持 status=已确认、owner=运维，待运维在其目录补齐模板后关闭。
