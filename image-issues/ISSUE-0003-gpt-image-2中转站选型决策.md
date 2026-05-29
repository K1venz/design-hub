---
id: ISSUE-0003
title: gpt-image-2 图生图中转站选型决策（诗云 vs apinebula）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 阻断生产选型：决定 composition.py 接哪家、failover 主备如何排
reporter: Research
owner: PM
created: 2026-05-29
updated: 2026-05-29
related:
  - market: image-market/2026-05-29-gpt-image-2-中转站对比-诗云vs apinebula.md
  - spec: docs/superpowers/specs/2026-05-28-gpt-image-2-failover-relay-design.md
  - code: image-issues/ISSUE-0002（adapter 实现缺陷，并行推进）
---

## 背景
主业务=图生图(image-to-image)，路线已定「gpt-image-2 + 合规」。已实测两家中转站，需 PM 拍最终选型，决定 composition.py 接哪家、主备双中转如何排序。

## 已验证事实（2026-05-29 实测）
| 维度 | 诗云 API | apinebula |
|---|---|---|
| 图生图 /images/edits | ✅ | ✅ |
| 出图质量/中文文案 | 优秀、零错字 | 优秀、零错字（与诗云同源） |
| 返回格式 | b64_json | b64_json |
| 实测扣费(1536×1024,medium) | 待核控制台（按官方价估 ≈¥0.44） | **¥0.1/次**（控制台已确认） |
| 错误码规范 | 待测（实测当下整站宕机） | OpenAI 标准(400/422/403/503)，干净 |
| 稳定性 | ⚠️ 实测当下整站 502 宕机 + 曾 429 | ⚠️ 撞过分组无渠道 503 |
| 资质 | 宣称等保三级+审计 | 疑号池/逆向网关 |
| 发票 | 宣称增值税票 | 客服口头称「可以开」（细节待确认） |

## 待 PM 决策/推进的动作
1. **【生死线】确认 apinebula 开票细节**（话术已备，见处理记录）：
   - 增值税专票 还是 仅普票？
   - 开票主体(销售方)是否国内正规公司？要全称 + 税号。
   - 票面项目名（技术服务费 / 信息技术服务费）？
   - 税点 / 最低门槛？
   → 若专票 + 正规国内主体成立：apinebula 合规过关。
   → 若个人代开 / 品名含糊 / 主体海外：票中看不中用，apinebula 出局。
2. **核诗云控制台**：本轮 3 张图真实扣费，与 apinebula ¥0.1 公平对比。
3. **诗云恢复后重测**（owner 可回 Research）：确认宕机是偶发还是常态。

## 候选结论（供 PM 参考，非最终）
- 若 apinebula 开票主体正规 → **推荐 apinebula(¥0.1,主,成本) + 诗云(有资质,备,合规兜底) 组主备双中转**，一便宜一稳妥互补，正好落地 failover spec。
- 若 apinebula 开票不合规 → 回退诗云为主，另觅第二家合规中转做备（如 API易，待测）。
- 风险提示：apinebula 即便能开"技术服务费"票，底层若为逆向 ChatGPT，业务在《生成式AI管理办法》《深度合成规定》下仍属灰色，能开票≠业务合规，PM 需评估公司风险偏好。

## 处理记录
- 2026-05-29 [Research] 创建，汇总两家实测结论，owner=PM。已向用户提供 apinebula 开票追问话术（专票/主体全称税号/品名/税点/门槛）。
