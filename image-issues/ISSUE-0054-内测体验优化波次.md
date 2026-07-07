---
id: ISSUE-0054
title: 内测体验优化波次（移动端响应式三档 + 成果区栅格懒加载 + chat P3 打磨）
status: 已修复        # coordinator 独立复验 6 条全绿 + 零迁移轮上线 prod(bundle index--Owrukjq)；随用户复核批次终关
severity: P2          # 内测体验打磨：移动端不可用=真实阻断面(P2 偏高)、成果区形态用户拍板、chat P3 隐私/话术打磨
reporter: PM          # coordinator #988/#989 派单 + 用户 07-07 拍板，PM 入档统一挂验收
owner: PM             # 已上线 prod、验收全绿；成果区栅格随用户复核批次(0048/0051/0053)，复核后 PM 终关
created: 2026-07-07
updated: 2026-07-07
related:
  - PRD: §3.14 ④成果展示区(🔄07-07 横滚→栅格+纵向懒加载)、§3.14 验收#4
  - issue: ISSUE-0048(新公开首页宿主)、ISSUE-0051(chat 会话)、ISSUE-0053(成果卡双按钮+配方弹卡)
  - issue: ISSUE-0052(白底剥离档A)——同 QA/部署波次抽验、但独立条目独立 owner(prompt+dev)
  - 群聊: image-gen#1 #988(优化队列派工)、#989(成果区栅格用户拍板)
---

## 定性（用户 07-07 放行整条优化队列，coordinator #988/#989 派工）
用户放行内测体验优化队列（**预授权：QA 绿即上线**）。coordinator 两线并行派工、写域不相交。本条统一挂**前端体验打磨 + chat P3 打磨**的验收与关账（0052 白底剥离同波次 QA/部署抽验，但独立条目、owner=prompt+dev）。

## 范围与分工

### A. frontend-b 线（image-web）
1. **移动端适配一揽子**（体检 Bug1+Bug3+优化1）：
   - **SideNav 加 md 断点**：<768 收**汉堡抽屉**（点击滑出+遮罩关+Esc 关；桌面 ≥768 不变）。
   - **公开首页窄屏单列堆叠**：Hero/6 快捷卡/工具区/成果区窄屏单列（390 档 Hero 标题/输入框恢复可用）。
   - **/set 工作台**：配置栏+结果栏窄屏**上下堆叠**（消 218px 横向溢出）。
   - **/history**：卡片窄屏单列。
2. **成果区形态改版**（用户 07-07 拍板，#989）：「看看实朴出的图」**废横滚 → 卡片栅格 + 纵向向下滚动懒加载**：
   - 栅格：桌面 3-4 列 / 平板 2-3 列 / 手机 1-2 列（与移动端断点一体）。
   - 纵向懒加载：底部 IntersectionObserver 哨兵进视口加载下一批（每批 6-8 张、13 张分两批、未加载批 skeleton 占位）；每张仍 per-image 懒加载；分批入场用现有卡片 motion（GPU 纪律）。
   - **卡片内容不动**（图+图型角标+caption+做同款/查看详情双按钮+配方弹卡，沿 ISSUE-0053）；空/错回落照旧。
3. **chat P3-#4（隐私）**：发送后消息明文进 URL（`?q=…`）→ 改 state/POST 承载，进会话后 replaceState 清 query。

### B. dev 线（image-code，顺序做）
4. **chat P3-#5（话术）**：澄清轮把 `upload_ids` 等**内部字段名直吐用户** → 校验失败信息过一层**用户话术映射**（如「请先上传 1–3 张产品图」）；**只改呈现不改校验语义**；顺手全扫 `launcher.validate` 的用户可见文案。
5. （接续）**ISSUE-0052 白底剥离档A组装侧**——独立条目，不在本条验收；同波次 QA/部署一并抽验。

## 验收标准（QA，coordinator 一轮验到位）
1. **响应式三档零横溢（P1）**：390 / 768 / 1440 三档 `documentElement` 零横向溢出。
2. **汉堡抽屉（P2）**：<768 SideNav 收汉堡、点击滑出 + 遮罩/Esc 关；桌面 ≥768 零回归（1440 像素级不动）。
3. **成果区栅格 + 懒加载（P1）**：三档栅格列数正确（桌面 3-4/平板 2-3/手机 1-2）+ 向下滚动触发第二批加载 + **双按钮/配方弹卡零回归**（ISSUE-0053 功能不受损）。
4. **chat URL 隐私（P3）**：发送后消息不留在 URL query（state/POST 承载 + replaceState 清 query）。
5. **chat 澄清轮话术（P3）**：校验失败不吐内部字段名、呈现为用户话术；**校验语义不变**（fail-fast 口径不动）。
6. **零回归（P0）**：桌面全链（首页/工作台/套图/复刻/编辑/历史/管理/chat）+ 现有懒加载/showcase 零变化。

## 范围外（YAGNI）
平板专属精调布局 / PWA / 触摸手势 / 成果区无限流分页后端化（13 张前端分两批够用）/ chat 富交互重构。

## 处理记录
- 2026-07-07 [PM] 用户放行整条优化队列（预授权绿即上，coordinator #988/#989 派工）→ PM 入档统一挂验收：
  ① 落 PRD §3.14 ④成果区 🔄07-07 形态改版（横滚→栅格+纵向懒加载）+ 验收#4 补三档栅格/第二批加载/双按钮零回归；
  ② 开本条统一挂**移动端响应式三档 + 成果区栅格 + chat P3-#4/#5** 验收 6 条。分工=frontend-b（移动端+成果区+chat URL）/dev（chat 澄清轮文案映射）并行、写域不相交；**ISSUE-0052 白底剥离**独立条目、同波次 QA/部署抽验。
  完工链=各自 commit → coordinator 拉 QA（响应式三档回归 + chat 文案 + 0052 白底真图抽验 ≤¥2）→ 绿即**零迁移轮部署**（deploy.sh+push.sh）。**仍内测灰度**（7.B/7.A 前置不变）。0050 排 0052 后（dev 先实测 prod tz）。真实用户 bug 随时打断。
  status=修复中、owner=frontend-b+开发（并行开工）。
- 2026-07-07 [dev] **chat P3-#5 澄清轮话术完成**（commit `513ca0b`，只改呈现不改校验语义）：
  澄清轮把 `upload_ids`/`plan`/`overlay_texts`/`ratio` 等内部字段名直吐用户 → 全扫用户可见校验文案改用户话术：
  ① `job_launcher.validate`（upload_ids 数量→「请上传 1–3 张产品图」、去裸 uid、产品图/参考图/delta-ratio）；
  ② `build_listing_prompts`（plan/n 互斥·overlay·张数·图型·套图总数·文案 全去字段名）；③ `ratio_to_size`（补可选项、无 "ratio" 字样）；
  ④ `prompt_composer`（下拉值/prompt/未知品类·图型 去内部措辞）；⑤ `orchestrator`（pydantic 解析失败不再吐原始报错、改话术澄清，
  与 validate 失败同为「LLM 产不可用参数→追问」收敛）。**异常类型/触发条件/校验语义全不变**。
  测试=内部字段名泄漏哨兵（listing_validation 全 fail-fast 用例断言消息无 upload_ids/plan/overlay_texts/modifiers/ratio/category
  + ratio 话术）+ 端到端（test_chat：upload_ids=[]→澄清含「请上传」、无内部字段名）。ruff+mypy(src) 绿、pytest 100 绿+1 已知 WIP 红。
  **dev 份（chat P3-#5）完成**，待与 frontend-b 前端份（移动端+成果区栅格+chat URL 隐私）一并 QA 验收。
- 2026-07-07 [frontend-b] **前端份完成**（commit `b3c5acd`，纯 image-web 10 文件，一提交）：
  **移动端适配（体检 Bug1+Bug3+优化1）**：① SideNav 响应式——桌面(≥md)静态侧栏不变、移动(<md)收汉堡抽屉（AppTopBar 汉堡按钮 md:hidden、
  AppShell 提升开合态传 SideNav/AppTopBar、抽屉 radix Dialog 原语+motion 滑出 spring、遮罩/Esc/点导航 关；NavContent 抽出桌面栏与抽屉共用）；
  ② /set 上下堆叠（218px 横溢根因=SideNav 恒占位+config 固定宽）——SideNav hidden md:flex 让全宽、WorkbenchLayout flex-col md:flex-row+移动
  overflow-y-auto、ListingConfigPanel w-full md:w-[372px]、ResultGallery md:flex-1 md:overflow-auto；/history auto-fill 天然单列。
  **成果区栅格+懒加载（用户 07-07 拍板）**：栅格 grid-cols-1/min-[440px]:2/md:3/xl:4（手机1-2·平板3·桌面4）；13 张分两批(7+6)、底部
  IntersectionObserver 哨兵进视口显现下一批、未加载批 skeleton 占位、每卡入场 motion（GPU 纪律）；卡片内容/双按钮/配方弹卡沿 0053 不动；per-image 懒加载/空错回落照旧。
  **chat P3-#4（首句明文隐私）**：Hero 首句改 navigate state 承载（不进 URL）；ChatPage 读 location.state.q 优先+兼容遗留 ?q= 外链、消费后
  replaceState 清 URL query+history state（防刷新重发）；LoginPage/RegisterPage 恢复受保护路由 from.state（prefill 分支不变）→ 登出态
  Hero→登录墙→登录后 /chat 自动发首条不丢（seed 随 from.state 存活、全程 URL 无明文）。
  **门禁四件套全绿**（lint/tsc/vitest 54/build）。**本地 mock + Playwright 三档 E2E 实证**：
  · 1440：零横溢·SideNav 显·无汉堡·成果区 4 列·下滚 7→13 分批·/set 两栏零回归；
  · 768：零横溢(/+/set)·SideNav 显·无汉堡·成果区 3 列·/set 两栏；
  · 390：零横溢(/+/set+/history)·SideNav 隐·汉堡·抽屉开合+点导航自动关·/set 上下堆叠·/history 单列·成果区 1 列；
  · chat：Hero 发送→/chat 无 ?q=·首句已发·state 已清；遗留 ?q=→自动发+query 剥离；登出漏斗 seed 过登录墙存活自动发·URL 无明文；
    做同款 prefill 登录后 /set 预填不回归。
  **验收 6 条自证**：#1 三档零横溢✓/#2 汉堡抽屉✓/#3 栅格三档列数+第二批+双按钮零回归✓/#4 chat URL 隐私✓/#6 桌面零回归✓（#5 chat 话术=dev 份）。
  **交接**：前端份交付、门禁绿+三档 E2E 全过 → @coordinator 一轮 QA（响应式三档回归+chat 文案+0052 白底抽验）→ 零迁移轮部署。owner→coordinator（前端份完成，dev 份 513ca0b 已就位）。
- 2026-07-07 [coordinator] **0054 波上线 prod**（#1002，零迁移、bundle `index--Owrukjq`、回滚镜像 `rollback-20260707-152527`、smoke 绿）：
  **时序=提前到 key 恢复之前部署**（依据：①出图因平台侧故障全断、0052 组装代码上不上线对用户无差别；②移动端适配/栅格/chat 隐私对正在浏览的用户是纯收益、压着没意义；③0054 全部验收项独立复验全绿）。
  **coordinator 独立复验 6 条全绿**：三档零横溢 / 汉堡开合 / 栅格 7→13 分批 / chat 无 ?q=+首句直达 / 澄清话术人话零字段名（**顺带实证 513ca0b 在真 LLM 上工作正常**）/ 桌面零回归。
- 2026-07-07 [PM] **状态机推进：修复中 → 已修复，owner→PM**。coordinator 独立复验 6 条全绿 + 零迁移轮上线 prod → 本波（移动端响应式三档 + 成果区栅格懒加载 + chat P3-#4/#5）修复闭环坐实。落 PRD §3.14 ④成果区 🔄改版转 ✅ 已上线。
  **时序修正认可**：coordinator 提前部署（key 前）依据成立、编排自主权内、对浏览用户纯收益、验收项独立复验全绿——非阻断决策，PM 无异议。
  **随用户复核批次终关**：成果区栅格=用户 07-07 拍板、用户下次登录看新首页自然可见（连同 0048/0051/0053 一并过目）→ 复核通过 PM 终关（已关闭）；移动端/chat 隐私=内测打磨已 prod 验证全绿。
  **注**：本条不含 0052（0052 独立条目、组装代码随本波上线但**关账 gate=key 恢复后 ¥2 真图抽验**、仍待验证）。
