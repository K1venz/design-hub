---
id: ISSUE-0036
title: prod mysql 3306 在宿主机 bind 0.0.0.0（公网暴露面，目前被安全组挡住）
status: 已确认
severity: P3
reporter: 运维
owner: 运维
created: 2026-06-08
updated: 2026-06-08
related:
  - host: 203.0.113.10 (Design-Platform-Main)
  - compose: /opt/docker/mysql/compose.yml
---

## 现象
prod 主机上 mysql 容器把 3306 端口 publish 到 `0.0.0.0`（`0.0.0.0:3306->3306/tcp`，
docker-proxy 监听）。即 MySQL 在宿主机所有网卡上可达，是一个公网暴露面。

## 期望 vs 实际
- 期望：MySQL 只对内部（docker 网络 / 127.0.0.1）开放，不 bind 公网。
- 实际：宿主机 `0.0.0.0:3306` LISTEN。

## 环境 / 上下文
- 本机（外网）实测：80→301、443→200 可达；**3306 外网 filtered/closed**
  → 当前云安全组把 3306 入站挡住了，**暂不可被外部利用**。
- 但「公网 bind + 仅靠安全组兜底」是脆弱姿态：安全组一旦误改、或同 VPC 内主机被攻陷，
  MySQL 即直接暴露。属纵深防御缺口。
- api↔mysql 走 docker 网络（mysql_default 172.18.0.x），**不依赖宿主机 3306**，
  故收紧 bind 不影响 api 连接。

## 建议修复
- /opt/docker/mysql/compose.yml 端口映射 `3306:3306` → `127.0.0.1:3306:3306`
  （或移除 publish，仅留 docker 网络互通）。
- 需 recreate mysql 容器（短暂断连），api 因走 docker 网络重连即可。
- ⚠️ 本轮 listing 验收期间 frontend-b 正经只读隧道走查 prod、勿随意重启；
  建议排一个低峰维护窗口执行，执行前群里知会。

## 处理记录
- 2026-06-08 [运维] 只读核查 prod 时发现，实测外网 3306 filtered（安全组已挡），
  判定 P3 非阻塞，归档跟进。状态=已确认，owner=运维，待维护窗口收紧 bind。
