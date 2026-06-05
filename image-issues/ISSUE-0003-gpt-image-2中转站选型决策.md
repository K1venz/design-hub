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
| 发票 | 宣称增值税票 | ✅ **已收样票：增值税普通发票(普票)，正规公司主体(有销售方名称+税号)，项目名"信息系统增值服务/信息服务费"** |

## 待 PM 决策/推进的动作
1. ✅ **【已闭环】apinebula 开票核实**：客服统一开「增值税普通发票」，销售方为正规公司(有名称+税号)，项目名"信息系统增值服务/信息服务费"合规。**用户确认普票够用(仅需报销入账，不需进项抵扣)→ apinebula 合规关通过。**
   - 残留小项(非阻断)：核对销售方公司全称是否与 apinebula 运营主体一致、税率几个点。
2. ~~核诗云控制台 / 诗云恢复后重测~~ → **作废，诗云已出局**。
3. **【新增·关键】补备用中转**：apinebula 定主后备用位空缺，需测第二家合规中转(GetGoAPI / API易)做备，落地真正的主备双中转。需用户提供候选家 key。
4. **PM 最终 go/no-go**：合规已过，待"备用家"确定后即可拍最终主备配置 → 交开发写 composition.py。

## 候选结论（供 PM 参考，合规关已过；诗云已排除）
- **诗云已出局**（2026-05-29 用户决定）：实测当下整站 502 宕机 + 价格未核，不再考虑。
- **apinebula 定为主**：¥0.1/次、质量好、错误码规范、普票合规均已验证。
- ⚠️ **备用位空缺，必须补**：诗云移除后 failover 只剩 apinebula 一家 = 单点故障，而 apinebula 自身撞过 503。需补第二家合规中转做备。三方案：
  - **A(推荐)**：apinebula(主) + 第二家合规中转(备)，候选 GetGoAPI(称¥0.08/次、普票/专票) 或 API易(对公开票)，待测。
  - B：apinebula 单跑，挂了由 pipeline 外层降级到国内模型(海螺/通义)——降级后非 gpt-image-2，风格突变。
  - C：apinebula 裸跑无备——放弃稳定性，不建议。
- **风险提示（仍需 PM 知悉）**：apinebula 底层疑逆向号池(分组命名"自建号池/逆向满血")。普票票面合规，但底层若为逆向 ChatGPT，业务在《生成式AI管理办法》《深度合成规定》下仍属灰色——**能开票≠业务合规，PM 评估公司风险偏好**；号池稳定性为结构性风险，主备 failover 是缓解手段。

## 最终决定（2026-05-29 用户拍板）
- **apinebula 单跑上线**：gpt-image-2 这条线先只接 apinebula 一家；备用中转**挂起待补**(非阻断，后续再测 GetGoAPI/API易)。
- **可接受性**：pipeline 外层已有"换模型"兜底(GPT_IMAGE_2 全失败→降级 SEEDREAM_5 等国内模型)，apinebula 全挂时图仍可出(降级后非 gpt-image-2)。故单跑为可接受过渡态。
- **给开发的实现提示（重要，省未来改动）**：composition.py 仍用 `FailoverModelProvider` 包 apinebula(即使只有一个 relay)，将来补备用只需往 relays 列表追加一家、零改代码(OCP)。不要图省事直接注册裸 OpenAICompatProvider。

## 处理记录
- 2026-05-29 [Research] 创建，汇总两家实测结论，owner=PM。已向用户提供 apinebula 开票追问话术（专票/主体全称税号/品名/税点/门槛）。
- 2026-05-29 [Research] 用户提供 apinebula 样票：增值税普通发票，正规公司主体(销售方有名称+税号)，项目名"信息系统增值服务/信息服务费"。用户确认普票够用(仅报销入账)。→ **apinebula 合规生死线通过**，动作1闭环。
- 2026-05-29 [Research] 用户决定**诗云出局**(宕机+不再考虑)。
- 2026-05-29 [Research] 用户拍板**apinebula 单跑上线、备用挂起待补**，剩余交 PM/开发推进。本 issue 决策部分完成，owner=PM 跟进 go + 后续补备用。
- 2026-06-05 [PM] **信息同步**（后端改动，用户告知）：`GPT_IMAGE_API_KEY` 支持逗号分隔多 key，`OpenAICompatImageProvider` 按请求 round-robin 轮询（`composition.py`+`openai_compat.py` 已实现），**缓解单 key 限流/配额**。
  ⚠️ 边界（避免误判，不改变本条"备用中转挂起"结论）：
  · 多 key = **同家 apinebula**，**≠ 备用中转**——本条「补第二家中转(GetGoAPI/API易)」单点风险**仍挂起未解**；
  · 缓解对象是「单 key 限流」，非「apinebula 整站故障」（实测撞过 502/503，多 key 一起挂）；
  · 坏 key 韧性缺口：某 key 失效(401/403) 按现 4xx-不重试逻辑 → 轮到它的请求直接失败、不自动跳过。
  用户确认**本次仅信息同步**，不排韧性/备用工作。owner 维持 PM（备用中转仍挂起待补）。
