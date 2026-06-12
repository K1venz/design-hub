# UI 主题系统令牌化迁移 · 可行性评估（dev 供料，Style 4「Glass SaaS」选定后）

> 背景：全站 UI 换肤（coordinator #717 用户选定 Style 4）。执行权=frontend-b（#720/#723
> 终裁，写入边界铁律）；dev 职责=本评估 + 39 hex 映射表（已贴群 #724）+ commit ① diff
> 蓝军核零视觉变更。数据为 2026-06-12 只读盘点，执行以 frontend-b 现场 grep 为准。

## 1. 现状：双色系分裂（frontend-b #709 报告，dev 量化坐实）

| 系统 | 位置 | 形态 | 覆盖 |
|---|---|---|---|
| A · shadcn oklch 令牌系 | index.css（66 处 oklch，`@theme inline` 映射 ~47 语义变量） | 组件经 `--color-*` 语义槽 | ui/ 原语 + 登录/注册/admin/dashboard 等 shadcn 页 |
| B · 硬编码 hex | **15 个 tsx、39 唯一值、~230 处**，全为 Tailwind 任意值 class（`bg-[#ece8e2]`） | 直接写死 | listing 工作台全 family + 布局层 + 历史两页 |

清洗域文件（15，排除 throwaway 的 pages/style-preview/）：
layout/{AppLayout, AppTopBar, WorkbenchLayout}、listing/{CloneConfigPanel, ConfigSelect,
EditConfigPanel, ImageUploader, ListingConfigPanel, PipelineBeam, ResultGallery,
WorkbenchRail}、project/CreateCustomerDialog、pages/{EditWorkbenchPage, HistoryDetailPage,
HistoryPage}。重灾区：EditConfigPanel(32 处)、HistoryDetailPage(29)、HistoryPage(23)、
ResultGallery(23)、ListingConfigPanel(19)。渐变 `from-[#7c6cff] to-[#ff9a62]` 共 4 处。

## 2. 映射表（39 hex → 6 语义簇，#724 已贴群；命名最终归 frontend-b taste）

| 簇 | token 建议 | 成员（频次） |
|---|---|---|
| A 纸面阶 | `--wb-surface-1..6` | #faf8f5(6) #fbfaf8(1) #f6f4f1(2) #f1ece5(1) #efeae3(1) #eee7df(1) |
| B 边框阶 | `--wb-border-1..4` | #ece8e2(39) #e7e0d6(2) #e4ddd2(2) #d8d1c6(1) |
| C 暖灰墨阶 | `--wb-ink-1..7` + faint-1..4 | #1c1b1a(8) #2c2824(15) #4a443d(5) #5b554e(4) #7a746c(4) #8a857e(17) #9b958c(10)；faint: #b8b2a8 #bdb6ab #b0a89c #cabfb0 |
| D 紫 brand 阶 | `--wb-brand-*` | #4733b8(14) #7c6cff(9) #a78bfa(2) #a855f7(2) #cdbfff(8)；tint: #ddd5f5(3) #f4f0ff(4) #f4f1ff(3) #f8f6ff(2) |
| E 暖橙阶 | `--wb-warm-*` | #ff9a62(5) #b08968(1)；深: #c2410c(5) #b45309(2) #C8442B(1)；tint: #f0c8b4 #f3d9c4 #fdf3ea #fdf6f2 |
| F 渐变对 | `--wb-grad-from/to` | #7c6cff → #ff9a62（4 处；frontend-b 计划 ② 把 to 端换 #7b6cf0，留对名即可） |

## 3. 迁移路径：两 commit 隔离（回归面切割的关键）

**commit ①「零视觉变更令牌化」**（frontend-b 执行，dev 蓝军核）
- index.css 增 token 定义块，**值原样进变量**；15 文件任意值 class 机械替换。
- 硬规则：**不同 hex 值绝不共 token**（并阶/收敛近似值=视觉决策，归 ②）；不动布局/
  结构/逻辑/文案。
- **⚠️ shadcn 槽不能在 ① 复用**（#724 蓝军修正，本评估最重要的一条）：--border/
  --background 等槽现值=系统 A 冷调 oklch，工作台类直接指过去 → 像素必变；在工作台
  子树重赋槽值 → 子树内 ui/ 原语跟着变色，同样破零回归。∴ ① 必须走独立 `--wb-*`
  命名空间承载原值；**并轨是终态不是起步**。
- 验收=build 后像素级 diff：style-preview 基建正好可复用（同 fixture 截图 ①前后对比），
  或 prod 页面抽样截图比对。vitest 文案闸不受影响。

**commit ②「Style 4 值替换 + 并轨收敛」**（frontend-b）
- Style 4（浅灰 #f3f4f8 底 + 白卡软投影 + 单紫 #5b5bd6 accent）把两系配色对齐 →
  此时把 --wb-* 收敛进 shadcn 语义槽（或保留 alias 指向槽），一组 :root 值通吃全站，
  登录/admin 等系统 A 页自动跟。频次说明收敛潜力大：39 值高度长尾（24 个值 ≤2 次），
  ② 并阶后预计 ~12-16 个有效槽。
- 玻璃配饰（毛玻璃 panel/pill 顶栏/软投影）+ 布局比例精修同 commit 或随后增量。

**commit ③「动画丝滑」**（frontend-b）：路由过渡/微交互/SSE shimmer，复用既有 motion
依赖；与令牌系正交，不影响本评估结论。

## 4. 工程量与风险

- ① 机械替换 ~230 处/15 文件 + token 块：0.5-1 天（含像素 diff 验收）；②③ 为设计主活。
- 风险 R1：具名色（`bg-white`/`text-white` 等）与可能的 rgba()/oklch 内联不在 hex grep
  范围，① 时顺手清点（白卡在 Style 4 仍是白，风险低但要显式过一遍）。
- 风险 R2：渐变 4 处与 D/E 簇耦合（渐变端点同时是独立用色），① 拆对名后 ② 改 to 端
  即全局生效——这是令牌化的直接收益演示。
- 风险 R3：① 若混入任何值收敛（如 #fbfaf8 并入 #faf8f5），零回归承诺破——蓝军 review
  的第一检查项即 token 定义块的值与映射表逐一对照。

## 5. 结论

可行性高、路径清晰：底座（Tailwind v4 CSS-first + shadcn 纪律）对换肤天然友好，唯一
真实工程量是系统 B 的 15 文件清洗，且两 commit 切割使回归面可控（① 像素零变更可机器
验证、② 才是视觉变更需 coordinator 截图过用户）。dev 后续动作=commit ① diff 蓝军核
（检查项：token 值原样/无值收敛/无布局结构改动/shadcn 槽未被 ① 复用）。
