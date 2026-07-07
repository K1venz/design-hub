# 效果图「配方展示 + 一键复用」设计稿

- 日期：2026-07-07
- 来源：用户需求「效果图展示里做提示词复用——展示图片同时展示生成配置与提示词」
- 状态：coordinator 定稿派单（口径决策已向用户亮明：展示「配方」而非内部完整 prompt）

## 一、核心口径（本稿最重要的一条）

**展示与复用的对象 = 「配方」= 用户可复用输入**：图型（白底/场景/卖点）、比例、张数、平台、风格描述（listing_job.prompt=用户自由文本）、卖点文案、modifiers。

**不展示组装后的完整内部提示词**，三个硬理由：
1. 根本没存——listing_job.prompt 只存用户自由文本，卡体系组装的完整 prompt 用完即弃（读码实锤）；
2. 卡体系 = 核心商业资产（"提示词是唯一质量杠杆"），公开页展示 = 泄漏给竞品；
3. 产品无完整 prompt 输入口（prompt 恒走卡链），展示了也无法复用——展示配方才是可复用的闭环。

## 二、两个落点

### A. 出图历史（自己的图）——纯前端，数据已齐
- `GET /listing/jobs/{id}`（ListingJobDetailOut）已回吐 prompt/modifiers/platform/ratio/size/n/每张 image_type/clone_mode/edit_mode——**后端零改**。
- UI：历史详情页加「查看配方」（抽屉/弹层：图型配比、比例、风格描述、文案、平台、风格参数；复刻/编辑单额外显示模式徽标）+ **「复用配置出图」按钮** → 跳 `/set` 预填。
- 工作台结果卡（最近一单视图）同样给「复用配置」入口（同一详情数据源）。

### B. 首页成果展示区（公开获客）——小后端 + 前端
- `ShowcaseEntry` 扩字段：`recipe`（styling 摘要/ratio/图型/文案要点），值从 prod 那 5 单真实 job 回填（读 prod DB 只读查询，人工写死进静态清单；**零迁移零建表**）。
- `GET /showcase` 响应加 recipe；依旧无鉴权无用户数据。
- UI：展示卡 hover/点开显示配方 + **「做同款」按钮**——未登录 → 登录墙 → 回跳携带配方 → `/set` 预填。

## 三、预填机制（前端契约）

- `/set` 接收预填：`navigate('/set', { state: { prefill: {...} } })`；workbench-store 加 `applyPrefill(prefill)`（覆盖 config/styling/文案，**不带 uploads**——产品图必须用户自己传，配方≠素材）。
- 登录墙回跳已有 `location.state.from` 机制，prefill 挂同一 state 随行。
- 预填后用户可改任何项再生成——配方是起点不是锁定。

## 四、范围外（YAGNI）

- chat 结果卡配方入口（后续小补）；配方分享链接/配方库；复刻/编辑单的「复用」（仅展示配方徽标，复用按钮只做套图单）；overlay 文案的逐张映射（展示 job 级要点即可）。

## 五、验收要点

1. 历史详情/结果卡可看配方，「复用配置」到 /set 各项预填正确（图型配比/比例/风格描述/文案）。
2. showcase 卡配方展示；未登录点「做同款」→ 登录 → 回跳 /set 预填不丢。
3. 任何响应/界面**不出现内部卡 prompt 内容**（口径①）。
4. 预填不带 uploads；用户改动预填项后生成按改后值走。
5. 老工作台/历史/showcase 零回归。

## 六、分工

- **dev**：ShowcaseEntry+recipe 扩展 + prod 只读查 5 单 job 回填 + ShowcaseItemOut/openapi 再生（零迁移）。历史侧确认零改。
- **frontend-b**：A+B 两落点 UI + /set 预填机制 + codegen。
- **QA**：验收 5 条。
- **部署**：deploy.sh（showcase 后端）+ push.sh，零迁移轮。
