---
id: ISSUE-0053
title: 效果图「配方展示 + 一键复用」——展示可复用配方（非内部卡 prompt）+ 一键预填出同款
status: 修复中        # spec 定稿派单、dev+frontend-b 并行开工中（feature 走 issue 生命周期）
severity: P1          # 用户直接提需求；获客/复用闭环（成果区做同款 + 历史复用配置）
reporter: PM          # 用户提需求（coordinator #971 转达），spec 定稿 ec9e80a，PM 入档
owner: 开发+frontend-b # 并行：dev 落点B后端(recipe字段+prod只读回填)、frontend-b 落点A+B UI+预填机制
created: 2026-07-07
updated: 2026-07-07
related:
  - PRD: §3.15 效果图配方展示 + 一键复用
  - spec: docs/superpowers/specs/2026-07-07-recipe-reuse-design.md（coordinator 定稿 ec9e80a）
  - issue: ISSUE-0048（新公开首页/成果区=落点 B 宿主）、§3.14 ④成果区（GET /showcase 13 张）
  - code: image-code showcase（ShowcaseEntry/GET /showcase）、listing 历史（GET /listing/jobs/{id} ListingJobDetailOut）；image-web /set + workbench-store
  - 群聊: image-gen#1 #971（coordinator 派单）
---

## 定性（用户提需求 2026-07-07，coordinator #971 转达）
效果图展示里做**提示词复用**：展示图片的同时展示**生成配置与提示词**，可**一键复用出同款**。spec 定稿入库、coordinator 派单。

## ⚠️ 契约裁决（PM+coordinator 2026-07-07，frontend-b #973 亮缺口后一致裁 (a)）
`overlay_texts`（卖点文案）**未持久化**——`listing_job` 无此列、请求期输入组装进卖点图后即弃、`ListingJobDetailOut` 不回吐 → 落点 A 取不回、落点 B 查不到。**裁决 (a)：卖点文案剔出配方复用范围（v1）**。理由：① 卖点文案本就是用户自己产品的卖点，做同款要的是版式质感（图型/比例/风格描述），文案必然自填；② (b) 加列持久化=破「零迁移零建表」+ 触发 DB 签字铁律、为边际召回便利不划算（YAGNI）；③ (c) 只 B 反推=两落点不一致+人工脆弱，否。→ **recipe 收窄 = styling/ratio/图型/platform/modifiers（无文案）**，A/B 预填口径完全一致（都不填 overlayTexts、用户自填）。overlay_texts 持久化留 backlog（若未来要文案召回=另立签字迁移件）。coordinator 同步改 spec §一/§五#1、PM 改本条与 PRD 验收。

## ✅ 核心口径（铁律·本条最重要）
展示与复用的对象 = **「配方」= 用户可复用输入**：图型（白底/场景/卖点）配比、比例、张数、平台、风格描述（`listing_job.prompt`=用户自由文本）、modifiers（**卖点文案剔出·见上裁决**）。
**绝不展示组装后的完整内部卡 prompt**，三个硬理由：
1. **根本没存**——`listing_job.prompt` 只存用户自由文本，卡体系组装的完整 prompt 用完即弃（读码实锤）；
2. 卡体系 = **核心商业资产**（"提示词是唯一质量杠杆"），公开展示 = 泄漏给竞品；
3. 产品**无完整 prompt 输入口**（prompt 恒走卡链），展示了也无法复用 → **展示配方才是可复用闭环**。

## 两个落点
- **A. 出图历史（自己的图）——纯前端、数据已齐、后端零改**：`GET /listing/jobs/{id}`（ListingJobDetailOut）已回吐 prompt/modifiers/platform/ratio/size/n/每张 image_type/clone_mode/edit_mode。UI=历史详情页「查看配方」抽屉（图型配比/比例/风格描述/平台/风格参数 + 复刻·编辑单模式徽标）+ **「复用配置出图」→ 跳 `/set` 预填**；工作台结果卡同给「复用配置」入口（同一详情数据源）。
- **B. 首页成果展示区（公开获客）——小后端 + 前端**：`ShowcaseEntry` 扩 `recipe` 字段（styling 摘要/ratio/图型/platform/modifiers，**不含文案**），值从 prod 那 5 单真实 job **只读回填**、人工写死进静态清单（**零迁移零建表**）；`GET /showcase` 响应加 recipe、依旧无鉴权无用户数据。（showcase 卡 caption 本就概括图上文案风味、展示层不缺表达。）UI=展示卡 hover/点开显配方 + **「做同款」→ 未登录跳登录墙 → 回跳携配方 → `/set` 预填**。

## 预填机制（前端契约）
`navigate('/set', { state: { prefill: {...} } })` + workbench-store 加 `applyPrefill(prefill)`（覆盖 config/styling，**不带 uploads·不带 overlayTexts**——产品图必须用户自己传、卖点文案用户自填，**配方≠素材**）；登录墙回跳复用现有 `location.state.from`，prefill 挂同一 state 随行；预填后用户可改任何项再生成——**配方是起点不是锁定**。

## 验收标准（QA，照 spec §五，文案项已按裁决剔除）
1. 历史详情/结果卡可看配方，「复用配置」到 /set 各项预填正确（图型配比/比例/风格描述/平台/风格参数；**文案不在配方=已知裁决、不验**）。
2. showcase 卡配方展示；未登录点「做同款」→ 登录 → 回跳 /set 预填不丢。
3. 任何响应/界面**不出现内部卡 prompt 内容**（口径①·核心资产不外泄）。
4. 预填不带 uploads；用户改动预填项后生成按改后值走。
5. 老工作台/历史/showcase 零回归。

## 范围外（YAGNI，二期）
chat 结果卡配方入口（后续小补）/ 配方分享链接·配方库 / 复刻·编辑单的「复用」（仅展示配方徽标、复用按钮只做套图单）/ overlay 文案逐张映射（展示 job 级要点即可）。

## 处理记录
- 2026-07-07 [PM] 用户提需求（coordinator #971 转达，spec 定稿 ec9e80a）→ PM 入档：落 PRD §3.15 + 开本条。
  **核心口径入档=展示「配方」非内部卡 prompt**（没存·核心资产不外泄·展示了也复用不了 → 展示配方才是可复用闭环）。
  分工（并行，写域不相交）：dev 落点 B 后端（ShowcaseEntry+recipe·prod 只读回填 5 单·零迁移零建表·历史侧确认零改）；
  frontend-b 落点 A+B UI + /set 预填机制（applyPrefill 不带 uploads·配方≠素材）+ codegen；QA 验收 5 条；
  部署=deploy.sh(showcase 后端)+push.sh **零迁移轮**（coordinator 编排）。**仍内测灰度**（7.B/7.A 前置不变）。
  status=修复中、owner=开发+frontend-b（并行开工）。**排队顺延**：移动端适配/chat P3/0052/0050 顺延本条后，真实用户 bug 仍随时打断。
- 2026-07-07 [PM+coordinator] **契约裁决 = (a) 卖点文案剔出配方复用范围**（frontend-b #973 亮缺口、PM #? 与 coordinator #974 独立同裁）：
  overlay_texts 未持久化（listing_job 无列·DetailOut 不回吐）→ A 取不回·B 查不到，与 spec「后端零改/零迁移」冲突。裁 (a)——文案剔出配方、
  不加列不签字、两落点一致（都不填 overlayTexts、用户自填）。**recipe 收窄=styling/ratio/图型/platform/modifiers（无文案）**。
  PM 同步改：PRD §3.15 加契约裁决段 + ①口径/②落点/③预填/④验收#1 剔文案；coordinator 改 spec §一/§五#1 标已知限制+backlog。
  overlay_texts 持久化留二期（要文案召回=另立签字迁移件）。dev recipe 字段照此收窄、frontend-b 前向兼容继续落点 A。裁决不阻断开工。
- 2026-07-07 [dev] **落点 B 后端完成**（commit `b86d4e0`，零迁移零建表）：
  ① `config/showcase.py`——新增 `Recipe`(category/ratio/plan 图型配比/styling 风格描述/modifiers)，对齐 ListingGenerateRequest
     套图**可复用子集**；**recipe 收窄口径已落**（无 overlay_texts、无 uploads、无内部卡 prompt）。
  ② **prod 只读回填 5 单真实配方**（07-02 showcase 批次 admin 名下、SSH 只读 SELECT，未写任何 prod 数据）：查得 5 job 的
     prompt(风格描述)/modifiers(region/language/platform)/ratio + 按 listing_image 统计图型配比(全 白1场2卖2)。13 张精选→5 单
     **归属映射由「品类×图型比例」确定**（花生 1:1淘宝/9:16抖音/16:9英文京东；润喉糖 3:4京东/1:1拼多多；抖音9:16 与京东3:4 像素同为
     1024×1536、由品类消歧），并与各 job 风格描述逐条印证（如 caption 暖木餐桌↔淘宝 prompt、蜂蜜↔京东 prompt、窗边↔拼多多 prompt）
     零冲突。分布 3/3/3/2/2=13。写死进静态清单。
  ③ 平台四值(淘宝天猫1688/抖音电商/京东/拼多多)与 `prompt_composer` 现值**完全一致** → 做同款预填走 launcher 校验通过（不会 400）。
     ratio 全在留档比例内、category=FOOD 已注册。
  ④ `showcase_schemas.py`——`RecipeOut` + `ShowcaseItemOut.recipe`；`openapi.json` 再生（+RecipeOut、ShowcaseItemOut.recipe，
     diff 仅 +46/-2 纯 recipe）。**GET /showcase 路由/历史侧(ListingJobDetailOut)零改**（DetailOut 已回吐全部配方字段，落点 A 后端零改属实）。
  ⑤ `tests/test_showcase.py`——200 形状含 recipe + 新增**配方卫兵**（图型配比键∈枚举/Σ3..10/本项图型在配比内/platform+language 非空/
     风格描述非空且**无内部卡组装标记泄漏**=验收③哨兵）。
  **验证**：ruff+mypy(src) 绿；pytest **97 绿 + 1 已知 WIP 红**(test_clone_blocks_match_card 未动)；全 13 项真实数据端到端序列化通过；
  styling 与 prod job.prompt 逐字一致（做同款忠实复现）。**交接**：openapi 已再生（含 recipe）→ @frontend-b 落点 B codegen 可切类型化；
  历史侧落点 A 后端确认零改可先行。owner 仍开发+frontend-b（我落点 B 后端棒完成，待前端集成 + QA 验收 5 条）。
- 2026-07-07 [frontend-b] **前端两落点完成**（2 提交，纯 image-web）：
  **落点 A**（`7443b3d`，后端零改）——① `lib/recipe.ts`（纯函数+9 单测）：`jobToRecipe(detail)` 从每张 image_type 计数反推套图
     图型配比、识别 set/single/clone/edit（**仅套图可复用**=spec §四「复用按钮只做套图单」）；`recipeToPrefill`→`Partial<ListingConfig>`
     （ratio 非法回退 1:1、plan/modifiers 深拷、**不含 uploads/overlayTexts**）。② `workbench-store.applyPrefill`：覆盖 config、清空
     uploads（配方≠素材）+ bump resetKey 重挂面板 + 清进行中态。③ `components/listing/RecipeDrawer.tsx` 配方弹层（复用 ui/dialog）——
     图型配比/比例/参数/风格描述 + 套图给「复用配置出图」→ `navigate('/set',{state:{prefill}})`；detail 由调用方已加载传入（DRY 不自拉）。
     ④ HistoryDetailPage 卡头 + WorkbenchPage 结果卡 headerAction（终态 job）挂「查看配方」；WorkbenchPage 消费 `location.state.prefill`
     → applyPrefill 后清 history state（防刷新/返回重复预填）。⑤ ResultGallery 加 `headerAction` 槽。
  **落点 B**（`398639e`，对齐 dev recipe 契约）——① codegen（cp openapi + gen:api，schema 含 RecipeOut/ShowcaseItemOut.recipe）；
     ② `showcaseRecipeToPrefill(RecipeOut)`（styling→prompt、plan 补齐三型、ratio 回退、+2 单测）；③ HomePage 成果卡加配方摘要
     （比例·套图张数·平台）+「做同款」——已登录 navigate('/set',{prefill})、未登录 navigate('/login',{from:/set, prefill})；
     ④ LoginPage/RegisterPage 登录/注册后转发 `location.state.prefill` 随行到目标页（含 token 已在的 Navigate 分支）。
  **门禁四件套全绿**：lint/tsc/vitest **54 passed**（+11 recipe 测试）/build。**本地 mock + Playwright E2E 实证**：
     · 落点 A——播种真实套图 job（plan 白底1/场景2/卖点3=6张·3:4·京东）→ 历史详情「查看配方」弹层配比/比例/参数/风格描述**精确** +
       **无内部 prompt 泄漏（验收③）** →「复用配置出图」→ /set 图型配比 1/2/3+比例 3:4+风格描述+平台京东**全部预填**、上传区空/生成禁用（**验收④不带 uploads**）；结果卡「查看配方」在位。
     · 落点 B——成果卡展示配方摘要（1:1·套图5张·淘宝天猫1688）；**登出态「做同款」→ /login 携配方（from=/set+完整 prefill）→ 登录 → 回跳 /set 预填正确**（平台/比例/风格描述/plan 5张全对）+ 生成禁用=uploads 未随行。
  **交接**：前端两落点交付、门禁绿+E2E 全过 → @coordinator 编排 QA 验收 5 条 → 绿即零迁移轮部署（deploy.sh showcase 后端 + push.sh 前端）。owner→coordinator（前端份完成）。
- 2026-07-07 [frontend-b] **落点 B UI 细化增量完成**（`bd09745`，用户 07-07 拍板、spec §二.B 更新 6a32f26、coordinator #979 派单）：
  showcase 卡从单「做同款」改**双按钮「做同款」+「查看详情」**；查看详情=**卡片式弹层（大图 + 配方全项，与 /set 配置项一一对应）** +
  弹层内做同款 CTA、**无需登录**（获客钩子）。① 抽出 `components/listing/RecipeFields.tsx`——配方全项定义列表（品类/图型配比/比例/
  参数/风格描述），归一 job 侧 Recipe 与 showcase 侧 RecipeOut 两来源（RecipeView 视图模型）；历史「查看配方」与 showcase「查看详情」
  共用（DRY/SOLID，展示件依赖 RecipeView 抽象）；RecipeDrawer 重构复用（行为不变，内联 dl→RecipeFields）。② `ShowcaseDetailDialog.tsx`——
  大图+图型徽标+RecipeFields+做同款 CTA，查看详情纯展示公开 recipe 无需登录、做同款由父级 onMakeSame 拦登录墙。③ HomePage 卡改双按钮行。
  **门禁四件套全绿**（lint/tsc/vitest 54/build）。**本地 mock + Playwright E2E 实证**：双按钮 13 卡齐；**登出态「查看详情」→ 弹层直开不跳登录**——
  大图 + 品类食品/图型配比 白底1场景2卖点2共5张/比例1:1/参数 地区中国·语言中文·平台淘宝天猫1688/风格描述**全项齐** + **无内部 prompt 泄漏（验收③）**；
  弹层内「做同款」→ /login 携配方（from=/set+完整 prefill）✓；**落点 A 回归**：RecipeDrawer 经 RecipeFields 渲染一致（配比1/2/3·比例3:4·参数·风格描述·复用配置出图）✓。
  **交接**：增量交付、门禁绿+E2E 全过 → @coordinator 拉 QA 按新 spec 跑 5 条（验收②扩双按钮+弹层）→ 零迁移轮部署。owner→coordinator。
- 2026-07-07 [frontend-b] **「查看详情」弹卡视觉/动画皮完成**（`d907694`，用户给参考件、coordinator #981/#982 派规格，零新增依赖）：
  ShowcaseDetailDialog 从基础弹层升级参考卡形——① 窄卡 max-w-sm 居中/rounded-xl 白卡+shadow-lg+p-6；顶部大图(rounded+图型角标)→
  居中标题(caption)+副标 → **发丝分隔行列表**(label 左 muted/value 右深色·border-b；行=品类/图型配比/比例/平台/地区·语言，与 /set 配置项
  一一对应)→ **末行「风格描述」无线+加粗强调+长文本换行成块** → **底部通栏 h-12「做同款」CTA(ui/button+品牌紫 bg-wb-brand)**。
  ② 动画=改 radix Dialog 原语+motion(motion/react)：容器 fade+scale(.95→1,.4s easeInOut)+**staggerChildren 0.1 逐行 spring(stiffness 100,
  y:20→0)弹入**+AnimatePresence 开合；GPU 纪律仅 transform/opacity；Content asChild=motion.div 保 radix a11y(role/focus-trap/Esc/overlay)
  +forceMount 交 AnimatePresence 控开合。功能面不变（双按钮/无需登录/弹卡内做同款拦登录墙）。
  **门禁四件套全绿**（lint/tsc/vitest 54/build）。**Playwright E2E**：登出态「查看详情」弹卡按参考卡形渲染（截图核对 大图/发丝行列表/末行强调/
  通栏紫 CTA）、全项配方齐、**无内部 prompt 泄漏**、**console 零报错**（motion+radix 干净）；弹卡内「做同款」→ /login 携配方不变。
  **交接**：视觉/动画皮落完、一次验到位 → @coordinator 拉 QA（一轮验全）→ 零迁移轮部署。owner→coordinator。
