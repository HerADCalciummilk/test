# nimm-algo-showdoc

用 Cursor Agent 按 NIMM 模板写/改算法 ShowDoc **插件页**与 **CLI 页**。

- 写页先套：`templates/plugin_page.md`、`templates/cli_page.md`；约束见 `SKILL.md`、`style.md`。
- 本文：安装、怎么用、对 Agent 说什么。

## 安装

1. 拷到 `.cursor/skills/nimm-algo-showdoc/`（或 `~/.cursor/skills/...`）。
2. 配置 ShowDoc MCP（**勿提交真实 token**）：

```json
{
  "mcpServers": {
    "showdoc": {
      "type": "streamable-http",
      "url": "https://www.showdoc.com.cn/mcp.php",
      "headers": {
        "Authorization": "Bearer <YOUR_SHOWDOC_TOKEN>"
      }
    }
  }
}
```

3. 确认 MCP 已连通。

| 用途 | 地址 |
| --- | --- |
| 项目 | https://www.showdoc.com.cn/2598854776811541 |
| 算法清单 | https://www.showdoc.com.cn/2598854776811541/11559060627551917 |
| 插件模板 | https://www.showdoc.com.cn/2598854776811541/11559060627552402 |
| CLI 模板 | https://www.showdoc.com.cn/2598854776811541/11559060627556703 |

## 安装后怎么用

1. **打开**目标算法代码所在工作区，确认 ShowDoc MCP 可用。
2. **对话里点名本 Skill**（`@nimm-algo-showdoc`），说清**包名**、建议带**代码路径**；需要时说明改哪些页 / 批量 / 检验（见下方话术）。
3. **未特别声明时**，Agent 默认同时写：
   - 插件页：基础说明 + 使用示例（**有本机可读真实样例则优先**；否则自建；适合可视化则出图）
   - CLI 页：基础说明 + 使用示例（场就绪 → `process(路径)` → print/图）
   - 有批量场景时另写「批量调度」
   - **默认不加**「检验结果」
4. **可裁剪**：明确说「只要插件页 / 只要 CLI / 只改示例」等。
5. **发布后**：按提示刷新 ShowDoc；图与 stdout 是否齐全见 `SKILL.md` 自检清单。

## 推荐说法

**基础（多数情况够用）**

```text
@nimm-algo-showdoc
按 Skill 改 <包名> 的插件页和 CLI 页。
代码路径：<包根>
```

也可用：`按 nimm-algo-showdoc，修改 generate_ancillary 的插件页和 CLI 页`（建议仍补上代码路径）。

**按需追加一行**（接在基础话术后）：

```text
只要插件页。 / 只要 CLI 页。
```

```text
无批量，不要写批量调度。
```

```text
要批量调度（业务路径）：输入 data/… ，辅料 … ，输出 … 。
```

```text
使用示例用真实数据：样例在 <本机路径>；（可选）裁到 <经纬范围 / 强降水区>。
```

```text
要检验结果：模式 <路径>，方法输入 <路径>，实况 <路径>，输出 <路径>；
窗口 <日期>；时区对齐 <如 EC 世界时、实况 BJT+8>。
先批量调度出方法结果，再算订正前/后 RMSE，写入 CLI 检验表（对齐模板对照表）。
```

```text
要数据图展示：图在 <目录>。（或由 Agent 调度后出图上传。）
```

```text
只改 CLI 使用示例，其它不动。
```

| 你宜说清 | 说明 |
| --- | --- |
| 包名 | 必说 |
| 代码路径 | 建议（Agent 本地读代码用；**勿写入发版 ShowDoc 正文**） |
| page_id | 改已有页时更稳 |
| 真实样例 / 检验路径 | 须为 **Cursor 本机可读**；不经跳板 SSH |
| 批量 / 检验 / 业务图 | 按需；检验须先调度再算，表含订正前/后 |

## Agent 会 / 不会

| 会 | 不会 |
| --- | --- |
| 按清单填种类/类别；真实样例优先 + `pcolormesh_2d_grid` 出图 | 编造/抄模板 RMSE；发版正文绑本机绝对路径 |
| 有批处理写批量，否则省略；CLI 图精简（1–2 张结果场） | 无批处理时硬凑批量；图题写「合成」；CLI 整套复刻插件多图 |
| 用户要检验且路径齐：先调度 → 再检验 → 写订正前/后对照表 | 跳板 SSH 连业务机取数；只写订正后一列；缺数仍填表 |
| 插件页末链 CLI、CLI 页末链插件 | 缺页脚互链 |
| 同要素「输入−结果」差值（订正类） | 「有输入−默认」差值；不可比量硬作差 |
| 同入口一条主路径示例即可 | 同入口再开第二个 `**使用示例**`；为参数表已写清的可选变体各堆一段示例 |
| 「算法功能与流程」画输入/入口/输出框架图 | 把内部算子步骤画成流程图（如梯度→幂次→缩放） |
| 上传真图并更新正文 URL | 反复 `delete_attachment` 卡住（旧附件网页手删） |

模板 CLI：https://www.showdoc.com.cn/2598854776811541/11559060627556703

## 相关文件

[SKILL.md](SKILL.md) · [templates/](templates/) · [style.md](style.md) · [outline.md](outline.md) · [categories.md](categories.md)
