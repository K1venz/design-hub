# gpt-image-2.0 提示词能力边界(一手调研存档)

> 调研日期 2026-06-01。用途:作为[通用宪章](../00-charter.md) §2 铁律的事实依据。
> ⚠️ **待 Ops/中转站确认**:我们网关返回的 `model` 字段实际是 `gpt-image-2` 还是 `gpt-image-1.5` 贴牌——两者在 §4 input_fidelity 上有关键差异。

## 一、版本谱系
- gpt-image-1(2025-04)→ gpt-image-1.5(2025-12)→ **gpt-image-2(2026-04-21 发布)**。
- 我们 enum 写的是 `gpt-image-2`(`domain/enums.py: ModelName.GPT_IMAGE_2`)。

## 二、长度 / 参数边界
| 项 | 结论 | 来源 |
|---|---|---|
| 提示词长度 | gpt-image-1 上限 32000 字符,2.0 同级或更高;**不是瓶颈** | OpenAI API 文档 |
| 真正瓶颈 | 指令越多越稀释,遵循度下降 → 少而精,小步单点微调 | OpenAI Cookbook |
| negative_prompt | **协议无此字段** → 一切约束正向化 | OpenAI Cookbook |
| quality | low/medium/high/auto;**小字密排必须 high** | CometAPI 文档 |
| size | 边长须 16 的倍数;1024² / 1536×1024 / 1024×1536 等;≤~3.6M 像素稳 | CometAPI 文档 |
| edits 输入 | 接受至多 16 张输入图;mask 需同尺寸同格式 + alpha 通道 | CometAPI 文档 |

## 三、文字渲染
- 官方称 2.0 文字准确率 **95–99%**,支持中日韩、曲面、小字、密排。
- **但**:密集装饰性小字仍是失败区(用户参考图的糊字/同款两张字不同即证据)。
- 可执行拉满:**引号锁原文 + verbatim + 标位置/字体/字号/颜色 + 精简文字量 + 小字用 quality=high**。

## 四、图生图 / 保真
- edit **默认只改你明确要求改的部分**,选择性重绘而非整图替换 → 外科手术式语言可保产品。
- 保留清单**每轮重述**以防漂移。
- ⚠️ **`input_fidelity` 参数在 gpt-image-2 被禁用**(官方称 2.0 默认即高保真),仅 1.5/1 可用 `low|high`。
  - 含义:2.0 **没有保真旋钮**可拧,只能靠外科语言 + 自查重抽。
  - **若实际是 1.5** → 可开 issue 让 Dev 加 `input_fidelity=high`,保真上一台阶。(见 ISSUE-0006)

## 五、真实感 / 反 AI(官方 + 站酷文一致)
- **保留"不完美"**:颗粒、失焦、硬阴影、偶然感、自然手持。
- **摄影语言**:镜头/焦距/光圈/景深/机位/胶片感(被宽松解读,用于定大方向而非精确仿真)。
- **主动索取真实质地**:`real texture, imperfections, honest and unposed, no heavy retouching`。
- **避免** "studio polish / staging / 8K / 电影级 / 商业广告质感" 等催生 AI 假感的词。
- 站酷文补充的品类侧重:食饮=东方克制/留白/治愈/生活方式;美妆=卖点清晰+一致性;科技=信息层级;时尚=高饱和/几何/超现实。

## 六、推荐结构顺序(官方)
场景/语境 → 主体/姿态 → 关键细节(材质纹理) → 构图(机位光影) → 文字(引号) → 约束(保留/排除) → 用途。
分段/短标签 > 一长段。生产系统优先"可读模板"而非花哨语法。

---
**Sources**
- OpenAI Cookbook — GPT Image Models Prompting Guide: https://developers.openai.com/cookbook/examples/multimodal/image-gen-models-prompting-guide
- CometAPI — How to Use and Prompt GPT Image 2: https://www.cometapi.com/how-to-use-and-prompt-gpt-image-2/
- MindStudio — What Is GPT Image 2: https://www.mindstudio.ai/blog/what-is-gpt-image-2-openai
- PromptHub — A Complete Guide to Meta Prompting: https://www.prompthub.us/blog/a-complete-guide-to-meta-prompting
- 站酷《GPT-image 2.0 提示词工程》: https://www.zcool.com.cn/article/ZMTc0NDU3Ng==.html
