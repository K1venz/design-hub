---
id: ISSUE-0061
title: 公开首页前加全屏品牌 Hero 首屏（100vh + 鼠标跟随彩带光轨动效）
status: 修复中        # 用户新需求、coordinator 消化参考件成规格派 frontend-b；纯前端轮、无后端无 DB
severity: P3          # 品牌/获客门面美化；非功能阻断、非资损；纯视觉增强
reporter: PM          # 用户 2026-07-08 给参考件提需求（coordinator #1078 消化派工），PM 入档
owner: frontend-b     # 纯 image-web（100vh Hero 区 + canvas 动效 TS 化改造 + 双 CTA 锚点）
created: 2026-07-08
updated: 2026-07-08
related:
  - PRD: §3.14 新公开首页（本条=首屏增补、现有 Hero/工具区/成果区整体下移一屏）
  - issue: ISSUE-0048（新公开首页宿主）、ISSUE-0054（成果区栅格=副 CTA 锚点目标）
  - 群聊: image-gen#1 #1078（coordinator 消化用户参考件成规格）
  - feedback: frontend-bold-aesthetic（视觉大胆、精选重磅配饰点睛）
---

## 定性（用户 2026-07-08 提需求，coordinator #1078 消化参考件成规格）
公开首页 `/` 前加**全屏品牌 Hero 首屏**（100vh），滚动/CTA 下滑进入现有首页内容。用户给了参考件（视觉/动效照搬骨架、文字全换实朴口径）。**纯前端轮、路由不动、SideNav 不动**（避 churn）。

## 放置
`/` 首屏加 **100vh 全屏 Hero 区** → 现有对话 Hero/工具区/成果区**整体下移一屏**；滚动或 CTA 下滑进入。

## 版式解剖（照参考件、文案换实朴）
1. **顶部胶囊公告条**：「✨ 全新上线：帮我设计 AI 助手 · 去体验 →」（点击滚到对话输入区）。
2. **巨型标题框**：四角「+」装饰 + 边框 + `mask-image:radial-gradient` 径向渐隐；大标题 `text-5xl/md:text-8xl`，文案建议**「一整套电商图，一句话的事。」**（frontend-b 可微调、与登录页文案区分）。
3. **标题框底部**：绿点 `ping` 动画 +「内测免费开放中」。
4. **副标题**：「实朴 · 电商图片工作站」+ 描述（白底/场景/卖点一次出齐、复刻爆款、文字保真——沿现有口径）。
5. **双 CTA**：主「开始创作」（滚到对话输入区；**未登录走登录墙老规矩**）+ 副 outline「看看实朴出的图」（滚到成果区）。

## 灵魂动效（参考件 canvas.tsx → TS 化改造，非照抄）
鼠标跟随彩带光轨——80 条弹簧物理丝带（spring/friction/tension/dampening 照参考）、色相 sin 流转（offset 285±85=青→蓝→紫→粉、贴品牌紫谱系）、`globalCompositeOperation=lighter`、strokeStyle hsla 低透明度。
**改造纪律（frontend-b）**：① 参考件是全局变量+ts-ignore 老 JS→重写干净 TS React 组件（useEffect 挂载+卸载**全清监听器**、勿泄漏）；② **移动端绝不劫持触摸滚动**（参考件 touchmove preventDefault 会锁死滚动→移动端禁用轨迹或仅 pointermove）；③ `prefers-reduced-motion`→静态渐变兜底；④ lighter 混合在浅色玻璃底会发白→Hero 首屏底色 frontend-b 定（可深色专屏或调混合模式）、保 Style 4 协调；⑤ **零新依赖**（motion/lucide/ui-button 现成）。

## 验收标准（QA/自证）
1. 门禁四件套（lint/tsc/vitest/build）。
2. Playwright 三档：Hero **100vh 不溢出** / 滚动进入原内容 / 双 CTA 滚动锚点（开始创作→对话输入·看看实朴出的图→成果区）正确 / **移动端可正常滚动**（不被 canvas 劫持）/ canvas 交互 console **零报错**。
3. 未登录点「开始创作」→ 登录墙老规矩（回跳继续）。
4. prefers-reduced-motion 静态兜底生效；卸载无监听器泄漏。
5. 零回归：现有首页 Hero/工具区/成果区（含 0054 栅格懒加载 + 0053 配方卡）下移后功能不变。

## 范围外（YAGNI）
多主题切换 / Hero 视频背景 / 参考件的触摸劫持行为（明确不搬）。

## 处理记录
- 2026-07-08 [PM] 用户给参考件提需求（coordinator #1078 消化成规格派 frontend-b）→ PM 入档：落 PRD §3.14 首屏增补 + 开本条。
  **纯前端轮、无后端无 DB 无签字**；路由/SideNav 不动（避 churn）；现有首页内容整体下移一屏。owner=frontend-b（100vh Hero + canvas TS 化 + 双 CTA 锚点），改造纪律=监听器卸载全清/移动端不劫持滚动/reduced-motion 兜底/零新依赖。验收=门禁+三档 Playwright（100vh 不溢出/锚点/移动端可滚/canvas console 零报错）+ 登录墙老规矩 + 首页下移零回归。完工 frontend-b commit+@coordinator → 纯前端轮部署 → PM 关账。真实用户 bug 随时打断。status=修复中、owner=frontend-b。
