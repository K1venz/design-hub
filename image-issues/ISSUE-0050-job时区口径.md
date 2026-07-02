---
id: ISSUE-0050
title: job 时间戳时区口径待统一（历史/详情时间显示口径）
status: 待复现        # coordinator #918 收口备忘另开小 issue；dev 细化根因/范围
severity: P3          # 轻微：显示/口径问题，不影响出图/计费/owner 隔离
reporter: PM          # coordinator #918 收口备忘，PM 入档占位
owner: 开发           # dev 细化根因（created_at 存储时区 vs 展示时区）
created: 2026-07-02
updated: 2026-07-02
related:
  - issue: ISSUE-0048（chat agent 上线收口备忘衍生）
  - 群聊: image-gen#1 #918（收口备忘：job 时区口径 P3 另开小 issue）
---

## 背景
coordinator #918 收口备忘列出「job 时区口径 P3、另开小 issue」。PM 入档占位——**具体根因/范围待 dev 细化**（PM 手头无 job 时间戳时区不一致的复现细节，只知 coordinator 列为 P3 轻微项）。

## 待 dev 明确
- 现象：job（listing_job / generation 时间戳）在何处显示时区口径不一致？（历史列表 / 详情页 created_at / SSE 事件时间？）
- 根因：DB 存储时区（UTC vs 本地）与前端展示时区是否统一？两阶段落库（5af8a04+2f82799）引入的『生成中』行时间戳是否同源？
- 影响面：纯显示口径、不涉计费/owner/出图正确性（故 P3）。

## 处理记录
- 2026-07-02 [PM] coordinator #918 收口备忘入档占位（P3 轻微、非阻断）。root cause + 范围待 dev 细化后转「已确认」。
  owner=开发（时间戳口径归代码侧）。若细化后发现涉迁移/schema=按铁律先报用户签字。
