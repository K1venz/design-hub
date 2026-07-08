---
id: ISSUE-0061
title: 公开首页前加全屏品牌 Hero 首屏（100vh + 鼠标跟随彩带光轨动效）
status: 已关闭        # 终版MarqueeHero已上prod(index-CzW3bUQA)+用户拍板「更好看」+案例页loose end随单CTA消解；无悬念
severity: P3          # 品牌/获客门面美化；非功能阻断、非资损；纯视觉增强
reporter: PM          # 用户 2026-07-08 给参考件提需求（coordinator #1078 消化派工），PM 入档
owner: —              # 已关闭：MarqueeHero终版上线prod、用户确认、案例页消解、无loose end
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

## 放置（⚠️ 用户 2026-07-08 在 frontend-b 窗口直接修订，覆盖 #1078 转述）
- **Hero 独立成完整页面 = index（`/`）**，**原首页（对话/工具/成果区）移 `/home`**（SideNav/登录跳转已同步）。**非**「叠在现有首页上方下移一屏」（旧转述口径作废）。
- **两段式**：第一屏=胶囊公告条+标题框**撑满整屏**；滚下去=副标题+描述+双 CTA。
- 副 CTA「看看实朴出的图」当前跳 `/home`（成果区）；⚠️ 用户提过「专门案例页」概念=**待用户明确**（见范围外/待澄清）。

## 版式解剖（照参考件、文案换实朴）
1. **顶部胶囊公告条**：「✨ 全新上线：帮我设计 AI 助手 · 去体验 →」（点击滚到对话输入区）。
2. **巨型标题框**：四角「+」装饰 + 边框 + `mask-image:radial-gradient` 径向渐隐；大标题 `text-5xl/md:text-8xl`，文案建议**「一整套电商图，一句话的事。」**（frontend-b 可微调、与登录页文案区分）。
3. **标题框底部**：绿点 `ping` 动画 +「内测免费开放中」。
4. **副标题**：「实朴 · 电商图片工作站」+ 描述（白底/场景/卖点一次出齐、复刻爆款、文字保真——沿现有口径）。
5. **双 CTA**：主「开始创作」（滚到对话输入区；**未登录走登录墙老规矩**）+ 副 outline「看看实朴出的图」（滚到成果区）。

## 灵魂动效（参考件 canvas.tsx → TS 化改造，非照抄）
鼠标跟随彩带光轨——80 条弹簧物理丝带（spring/friction/tension/dampening 照参考）、色相 sin 流转（offset 285±85=青→蓝→紫→粉、贴品牌紫谱系）、`globalCompositeOperation=lighter`、strokeStyle hsla 低透明度。
**改造纪律（frontend-b）**：① 参考件是全局变量+ts-ignore 老 JS→重写干净 TS React 组件（useEffect 挂载+卸载**全清监听器**、勿泄漏）；② **移动端绝不劫持触摸滚动**（touchmove **改 passive** 不劫持=纪律保留）；③ `prefers-reduced-motion`→静态渐变兜底；④ **底色=shadcn 浅色底**（⚠️ 非深色专屏——用户修订、1:1 照原参考件）；⑤ **零新依赖**。
**⚠️ 用户修订关键参数（1:1 照原参考件 Downloads/生图平台Hero页，#1078 转述丢参）**：底色 **shadcn 浅色底**（非深色）、**lineWidth=10**（非细线）、**dampening=0.025**（非 0.25）。

## 验收标准（QA/自证）
1. 门禁四件套（lint/tsc/vitest/build）。
2. Playwright 三档：Hero **100vh 不溢出** / 滚动进入原内容 / 双 CTA 滚动锚点（开始创作→对话输入·看看实朴出的图→成果区）正确 / **移动端可正常滚动**（不被 canvas 劫持）/ canvas 交互 console **零报错**。
3. 未登录点「开始创作」→ 登录墙老规矩（回跳继续）。
4. prefers-reduced-motion 静态兜底生效；卸载无监听器泄漏。
5. 零回归：现有首页 Hero/工具区/成果区（含 0054 栅格懒加载 + 0053 配方卡）下移后功能不变。

## 范围外（YAGNI）
多主题切换 / Hero 视频背景 / 参考件的触摸劫持行为（明确不搬）。
## ~~待澄清（用户）~~ ✅ 已消解（用户换版 MarqueeHero）
- ~~副 CTA「看看实朴出的图」目标~~ **消解**：用户 2026-07-08 拍板把 Hero 换成 **MarqueeHero 版**（单 CTA「开始创作」→/home、无副 CTA）→ **案例页 loose end 自然消失、无需再问用户**（frontend-b #1115）。

## 处理记录
- 2026-07-08 [PM] 用户给参考件提需求（coordinator #1078 消化成规格派 frontend-b）→ PM 入档：落 PRD §3.14 首屏增补 + 开本条。
  **纯前端轮、无后端无 DB 无签字**；改造纪律=监听器卸载全清/移动端不劫持滚动/reduced-motion 兜底/零新依赖。owner=frontend-b。
- 2026-07-08 [frontend-b+PM] **⚠️ 用户直接修订规格（在 frontend-b 窗口亲拍、覆盖 #1078 转述）+ Hero 交付 `2d8f26f`**：
  ① **Hero 独立成 index（`/`）、原首页移 `/home`**（SideNav/登录跳转已同步）——非「叠首页下移一屏」（旧口径作废、PM 已更放置段+PRD §3.14）；
  ② **底色=shadcn 浅色底**（非深色专屏）+ 动效参数 1:1 照原参考件（**lineWidth=10 / dampening=0.025**、touchmove passive 不劫持）——#1078 转述丢的关键参数已按原件移植；
  ③ **两段式**（第一屏胶囊+标题框撑满、滚下副标题+描述+双 CTA）。**用户已实机确认「效果很好」**。门禁四件套全绿 + Playwright 实证（标题框撑满/滚动两段/彩带成型/console 零报错/CTA→/home）。
  **可走纯前端轮部署**（随 Hero 波：+ dev input_fidelity 保真增强 + 品类真图精选入成果区 + 知识库品类行回写）。**副 CTA 案例页待用户明确**（见待澄清、不阻部署）。status 修复中→**待验证**（交付、待纯前端轮部署+PM 关账）；owner→coordinator（部署编排）。
- 2026-07-08 [frontend-b] **跟进修复 `68e72be`**（PM #1100 smoke 提醒点中）：路由改版后 Login/Register 的 backTo **无 from 默认从 `/`（现=营销 Hero）改回 `/home`（工作首页）**（带 from 回跳/prefill/q 随行不变）+ 404/403/协议页「返回首页」链接同步 /home。Playwright 实证注册成功落 /home、门禁绿。**Hero 波带 2d8f26f + 68e72be 一起**；smoke 三条（登录落 /home / 未登录见 Hero / 深链不 404）应全绿。
- 2026-07-08 [coordinator+PM] **✅ 上线 prod + 关账推进（#1110）**：从 main HEAD 构建（68e72be+2d8f26f 天然同包，bundle `index-JLOHJ2ij`）→ **真浏览器 smoke 三条全绿**：未登录 `/`=Hero（canvas 在、无工作台内容）✓ / 登录**落 /home**（实测 URL）✓ / 深链 /history 不 404 ✓。**PM 状态机推进：待验证 → 已修复，owner→PM**——**用户已实机确认「效果很好」（=最硬验收）+ prod smoke 三条全绿**，Hero 首屏闭环。落 PRD §3.14 转 ✅ 已上线。
  **唯一 loose end = 副 CTA 案例页待用户明确**（当前跳 /home 成果区兜底可用）：用户答「/home 够了」→ PM 终关 0061；用户要「独立案例页」→ PM 另立需求、0061 本条即可终关（案例页归新条）。PM 已向用户请澄清。
- 2026-07-08 [frontend-b+PM] **⚠️ 用户选型换版：Hero → MarqueeHero 版（`d7c22a6`+`a49115a`+`641c85f` 三颗一波，#1115）**：用户给 **21st.dev hero-3** 参考件、frontend-b 用项目栈重实现（白底 + 文字栈逐词 reveal + 描述半叠走马灯 + CTA 浮图上 + **底部实拍图无限走马灯**·渐隐 mask·卡片旋转错落），**用户对比后拍板「这个更好看」替换 index**。要点：① 走马灯=**12 张实朴真实出图转码 512px jpeg 打包 assets**（784KB、prod 可用、**零 API 依赖**）；② **初版彩带光轨（HeroLanding/RibbonCanvas）退役删除**（git 可回溯）；③ **单 CTA「开始创作」→/home**=用户选定布局 → **副 CTA 案例页 loose end 消解**（无需再问用户）。门禁四件套全绿 + Playwright 实证（/ 渲染新版 / 24 卡加载 / CTA→/home）。
  **本条状态**：Hero 概念已上线（初版 index-JLOHJ2ij），**最终版=MarqueeHero（d7c22a6）待纯前端波部署**（coordinator 从 main HEAD 构建）→ **上线 + smoke 绿后 PM 终关 0061**（案例页已消解、无 loose end）。owner→coordinator（部署）→PM（终关）。status 保持已修复。
- 2026-07-08 [coordinator+PM] **✅ 终版 MarqueeHero 上线 prod → PM 终关（已修复→已关闭，#1117）**：MarqueeHero 波已上 prod（`d7c22a6` 从 main HEAD 纯前端波、bundle `index-CzW3bUQA`）。**PM 终关**：用户选型拍板「更好看」（=最硬验收）+ 终版上线 prod + **案例页 loose end 随单 CTA 已消解、无悬念**。ISSUE-0061 **已关闭**。（PRD §3.14 Hero=MarqueeHero 定版已上线。走马灯 12 张实拍图打包 assets 零 API 依赖、初版彩带光轨退役。）
