# DESIGN.md — nimm-algo-showdoc 技能说明

## 全局视觉约定

### ① 画布与安全区
- 画布：1280×720；padding 上下左右各 60px；内容区 1160×600（x 60–1220, y 60–660）
- 页眉标题区：y 60–150；正文区：y 170–640；页脚：y 670（14px，仅内容页）
- 封面 / 结尾页可全出血；内容页不越安全区

### ② 配色方案（科技未来 · 深色冲击主题）
- 主色 accent：`#63A7D4`（冷蓝）；点缀冷蓝紫 `#4DA3FF`
- 底色 bg / deep_bg：`#0B1521`；深底文字 on_deep：`#FFFFFF`
- 文字：ink `#FFFFFF` / secondary `#A9CFE7` / body `#E7E8E9` / muted `#C9CCCE`
- 卡片底 surface：`#16233A`；分隔线 line：`#2C405C`
- 系列色：#24428F / #3A5CBC / #63A7D4 / #8FBCE4 / #E3F1F8 / #13263B
- accent 深档 `#0F1920` / 浅档 `#B9D7EC`
- 强调色一页 ≤2-3 处；结论条 accent 满底 + 深字

### ③ 字体系统
- 中文标题 / 正文：思源黑体（Source Han Sans / Noto Sans CJK）
- 西文与数字：Barlow Condensed（仅标题 / 大数字），正文西文随黑体
- 字号阶梯：封面主标 88 / 页面主标 36 / 卡片小标 24 / 正文 18-20 / 标签 16 / 脚注 14

### ④ 视觉母题
- 主标题下一根 1px 冷蓝渐变贯通细线（accent 35% 混底），只落主标题一处
- 页脚左下固定小标 `nimm-algo-showdoc` + 页码

### ⑤ 配图清单
- 无外部图片：全部用 Box / SVG / FAIcon 结构化图形，深色科技风
- 主色光晕：封面 / 结尾用 radial-gradient 冷蓝光晕 + 细网格线做科技氛围

---

## 逐页设计（5 页）

### P1 封面（含适用场景，原 P2 已并入）
- title: nimm-algo-showdoc
- type: cover / role: hero / rhythm: peak
- layout: 大字报式 + 深色光晕底，下半部并列三栏场景卡
- visual: 径向冷蓝光晕 + 点阵网格，主标题 80px，副标一行定位，产出标签行，下方三栏紧凑卡
- density: 字数约 150 / 图片 0 / 留白约 35%
- anti_pattern: 禁止把三栏写成痛点渲染；禁止独立成页；不加页尾
- description: 技能名 + 定位「按 NIMM 模板把算法代码写成 ShowDoc 页」+ 中性能力说明 + 产出标签（插件页/CLI页/示例出图检验）+ 三种适用场景（新建页/修改页/自检规范，由原 P2 合并而来）

### P2 它能做什么：输入 → 产出
- type: content / role: supporting / rhythm: valley
- layout: 流程链 g
- visual: 4 阶段横向流程（包名+代码路径 → 读代码/对清单 → 生成 → 插件页+CLI页），下方输出条
- density: 字数约 160 / 图片 0 / 留白约 25%
- anti_pattern: 禁止等宽卡片横排冒充流程；禁止无箭头无方向
- description: 输入包名和代码路径，技能读实现对清单，产出插件页与 CLI 页各一份（含使用示例，可选批量/检验）

### P3 快速上手：话术与 MCP 配置
- type: content / role: hero / rhythm: peak
- layout: 左标题色块 + 右内容（m），右侧上下两张代码块卡
- visual: 左侧大号「3 步」锚点，右侧上卡 CodeBlock ShowDoc MCP 配置（json，.cursor/mcp.json）+ 下卡 CodeBlock 调用话术（text）；先配置 MCP 再调用，符合使用顺序
- density: 字数约 220 / 图片 0 / 留白约 18%
- anti_pattern: 禁止把代码塞进窄卡角落；禁止等宽横排；两代码块卡高度须落在父容器内
- description: 安装到 .cursor/skills → 配 ShowDoc MCP（给出 streamable-http + Bearer token 的 json 示例，提示勿提交真实凭据）→ 对话里 @技能并说包名+代码路径；给出基础话术

### P4 标准工作流：十步收敛成六步
- type: content / role: supporting / rhythm: valley
- layout: 纵向流程 / 六步阶梯（g 变体）
- visual: 六步纵向编号节点：确认范围 → 对清单 → 读代码 → 套模板 → 写示例出图 → 自检刷新
- density: 字数约 200 / 图片 0 / 留白约 20%
- anti_pattern: 禁止超过 6 步挤在一页；禁止无编号无方向
- description: 把 Skill 内工作流浓缩为 6 个关键动作，标注每步产物；第 3 步读代码体现新 CLI 的四级合参；第 6 步为逐条自检 → 同步算法清单与进展页状态 → 请用户刷新；底部两栏卡：左「写页后同步」讲两页分工（对外清单不挂状态、内部进展页承担状态四档 + 数据标签，进展页不得对外展示），右「检验（按需）」保留原说明

### P5 写作规范：八条必守
- type: content / role: supporting / rhythm: valley
- layout: 左标题色块 + 右内容（m）长清单分组
- visual: 左侧「写作规范」大标题色块，右侧 4 组 × 2 条要点（数据/绘图/CLI/结构）
- density: 字数约 320 / 图片 0 / 留白约 15%
- anti_pattern: 禁止等宽多栏平铺；禁止使用「红线 / 返工」等情绪化措辞
- description: 真实样例优先、示例即算法输入（重网格/裁剪等预处理只在引导句说明，代码只有读数据→调用→print）、可移植导入；同要素订正前后共用色标；CLI 签名只写 process(...) 不写装饰器字样、三种调用 python -m / nimm_cli / import、直接用返回场；插件页签名→功能说明→参数→示例、图题不写合成、差值禁有输入-默认、页末互链、改图换新 URL

> 原 P6「结尾：文件索引与使用边界」已删除：索引多为维护者查用信息（且 cli_organization.md 已从 skill 移除），边界信息已在 P3（SSH 取数）、P4（默认不加检验、进展页为内部页）覆盖，无需独立成页。

---

## 合并版：nimm-skills-overview.pptx（13 页）

汇总三份 NIMM Skill：`nimm-algo-showdoc`（5 页）、算法改造规范要求（1 页）、`nimm-algo-review`（新建 3 页），前置总封面与目录，每部分各有分册封面。三份原文件保留不动。

| 页 | 来源 | 内容 |
|---|---|---|
| P1 | 新建 `slides/00-cover.slide` | 总封面「NIMM 相关 Skill 说明」+ 四标签（文档生成 / 模块结构 / 算法审核） |
| P2 | 新建 `slides/00-toc.slide` | 三栏目录：01 showdoc（P3–P7）、02 算法改造规范（P8–P9）、03 algo-review（P10–P13） |
| P3–P7 | 原 `slides/01–05.slide` | showdoc 技能说明 5 页（封面/能做什么/快速上手/工作流/写作规范） |
| P8 | 新建 `slides/00-part2.slide` | 第二分册封面「算法改造规范要求」 |
| P9 | 原 `nimm-module-structure.pptx` 的 slide1.xml | 七级目录 7 行 + process 四步 + 参数优先级条 |
| P10 | 新建 `slides/00-part3.slide` | 第三分册封面「算法包本地审核」：副标为流程链「静态检查 → 实跑 pytest → 语义复核 → 报告」，说明「任一步发现问题不中断，跑完再写报告，严重程度看退出码」，四标签 |
| P11 | 新建 `slides/00-review-ways.slide` | **两种使用方式**对比表：谁运行 / 语义复核由谁完成 / 需要 API Key / 适用场景；底部环境准备（Python 3.10+、装 requirements.txt，flake8 / packaging / openai 各自用途，被审包依赖自动建临时环境） |
| P12 | 新建 `slides/00-review-usage.slide` | **在对话里让智能体审核**：提示「每一步都由智能体完成，无需手动运行命令」；怎么说（三种话术 + /nimm-algo-review）；智能体六步；为什么程序分两次运行（三参数为智能体专用、日常无需关心）；边界 5 条 |
| P13 | 新建 `slides/00-review-manual.slide` | **手动运行与 API 调用 LLM 模型复核**：① 配置 LLM（三项、llm.toml 或环境变量、环境变量优先）② 运行（PYTHONPATH + python -m local_review）③ 看结果（md/json、退出码 0·1·2）④ 不配 API 时的调试参数 |

- P9 未用 DSL 重写：直接搬运原始 slide XML，零失真（38 个形状、文本与字号/颜色全部保留）；把 60 处 `schemeClr` 固化为原主题色（`accent1`→`4F81BD`、`lt1`→`FFFFFF`），rels 改指向 `slideLayout1` 并去掉 notes。
- 合并方式：因模块页须留在 P9、第三部分排在其后，DSL 基底生成 13 页并在 P9 放占位页（`00-placeholder.slide`），再用 zipfile 将 slide9.xml / 其 rels 替换为模块页原始内容；无需改 presentation.xml / rels / Content_Types。
- 第三部分内容按用户更新后的 `README.md`（11-26 16:43，新增「两种使用方式」对比表、「环境准备」「复核结果文件 llm.json」等章节）重写，取代原先基于旧 README/SKILL 的四页结构。原 `00-review-flow.slide`（两段式审核）已删除——其要点已由 P10 流程链、P12「智能体六步 + 为什么分两次」覆盖，避免重复。
- 页职责：P10 定位与流程，P11 选哪种方式（含共同环境准备），P12 对话怎么用，P13 终端怎么跑。
- 用户既有改稿已保留：P12 标题「在对话里让智能体审核」（去掉「主路径：」前缀）、P13 标题「手动运行与 API 调用 LLM 模型复核」；不写「主路径 / 备用路径」这类标签式措辞。
- 不写「大模型」修饰智能体：API 路径同样是大模型，区别在对话内 vs 程序调 API。
- 新页源文件：`00-cover / 00-toc / 00-part2 / 00-part3 / 00-review-ways / 00-review-usage / 00-review-manual.slide`，均单独通过 lint。
