# CLI 页套用模板

写/改 CLI 页时：从下方「整页骨架」起**整段复制**到 ShowDoc，替换全部 `{{…}}`。  
勿抄温度降尺度线上页的业务路径、检验数字与整套插件复刻图。有检验时**表式**对齐模板（订正前/后），数字须自算。约束见 `../SKILL.md` / `../style.md`。

仓库 CLI 已统一 `CliBase`：**对外签名写 `XxxCli.call`**（与命令行 flag 同名关键字），**不要**把模块内 `process` 当 CLI 页主签名。

---

**基础信息**
- **所属包**: `{{PACKAGE}}`
- **插件页**: [{{PACKAGE}}]({{PLUGIN_PAGE_URL}})
- **调度脚本**: `{{cli/xxx.py}}`

{{一段话：本页是 CLI 使用说明；算法参数见插件页。样例数据来源一句话（如来自 EC 模式场），勿堆「同域裁剪真场」术语。说明有/无批量。}}

**参数优先级**（由高到低）：**显式传入**（命令行 flag / `XxxCli.call(...)`）**>** **配置文件参数**（ini 非空项）**>** 代码预设默认值。空 ini 项不覆盖上层已给出的值。

**怎么跑**

（发版环境：本包已可导入。不要写「把 `00temp` 加入 PYTHONPATH」。）

```bash
python -m {{PACKAGE}}.cli
python -m {{PACKAGE}}.cli {{subcommand}} --help

# 必填无方括号；可选写在 [] 内
python -m {{PACKAGE}}.cli {{subcommand}} \
  --{{required-path}} PATH [--{{optional-path}} PATH] [--output-path PATH] [--config PATH]

# 等价：直接跑脚本
python {{cli/xxx.py}} --{{required-path}} PATH ...
```

{{说明：无子命令时打印用法；带子命令把后续 argv 转给对应入口。点明：无 [] = 必填，[] 内 = 可选。Python 对外为 XxxCli.call（返回退出码）。}}

<!-- 下表只列「可从命令行启动的入口」。禁止把 process / XxxCli.call 写成表的一行。
     三种常见形态：
     1) 有子命令：`python -m pkg.cli lapse-rate` → 表列子命令名；
     2) 无子命令、仅 `python -m pkg.cli` 打印用法：表可省略，或一行说明「只打印用法」；
     3) 另有 `python -m pkg.cli.xxx` 能直接跑脚本 __main__：应写入「怎么跑」代码块与表（脚本列 cli/xxx.py）。 -->

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| `{{有则填；无分发可写「无」或省略整表}}` | `{{cli/xxx.py}}` | {{做什么；可写 `python -m pkg.cli.xxx`}} |

# {{script_name}}

**调用插件**: `{{EntryName}}`

对外 Python 入口为 `{{XxxCli}}.call`（关键字与 flag 同名）。未传入的可选项为 `None`，按参数优先级回落。

<!-- 签名 div：只改内层；星号写成 &#42; 以免 Markdown 斜体把字变黑 -->
<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">{{XxxCli}}.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;{{required}}=...,<br>&nbsp;&nbsp;&nbsp;&nbsp;{{optional}}=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">{{name}}</span> | {{路径/调度含义；对应 `--flag`；省略时回落默认可写清}} |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功）。场写入 `output_path`（若给定）；需要 `DataArray` 时再读该 nc |

**使用示例**

{{引导句：数据来源与分辨率；用 XxxCli.call 写盘后再读场作图。命令行用法只在「怎么跑」，此处不要再贴重复 bash。注释写清「调度写盘 / 读出场」，勿写「与注释一致」这类读者无上下文的话。}}

```python
# 调用代码：场就绪 → XxxCli.call(... output_path=...) → 读场 → print
# 注释标明来源与分辨率；发版正文禁本机绝对路径
```

```
{{方法数据结果展示：print(场对象)；勿只打 name/shape；call 本身只返回退出码，应对读回的场}}
```

```python
# 画图代码（与调用分开）：中文图题先设 YaHei/SimHei
# 单场格点 pcolormesh_2d_grid；对照 creat_axs + add_contourf(..., cut_colorbar=False)
# 同要素可对照：须画订正前+订正后，共用 cmap/clevs；禁止只画结果场
# 勿整套复刻插件页（默认不贴差值/辅料/其它入口多图）
```

{{![订正前图题](url) 与 ![订正后图题](url) — 同要素两张；不可对照时仅结果场}}

<!-- 多 CLI 入口则再复制一个 # 节 -->

# 批量调度示例

<!-- 无目录/多时次/runner 批处理则整节删除。有则保留；数据可用业务路径示意，不强制自建一批 nc。 -->

{{带注释的批处理代码，优先 XxxCli.call；能画结果场则贴图}}

---

插件说明请见 [{{PACKAGE}}]({{PLUGIN_PAGE_URL}})。

---

## 可选块（默认不加）

用户明确要求检验、并给出**本机可读**的模式 / 方法输入 / 实况路径时追加。流程：**先批量调度出方法结果 → 再检验 → 写表**（见 `SKILL.md`）。不经跳板 SSH。

```markdown
## 数据图展示

（业务个例多图；使用示例已贴图时可不再单开）

## 检验结果

相对同时效实况，窗口 …：

| 项目 | 订正前 | 订正后 |
| --- | ---: | ---: |
| mean_bias | **…** | **…** |
| mean_rmse | **…** | **…** |
| Δrmse | — | **…** |

| 起报.时效 | 订正前 bias | 订正前 rmse | 订正后 bias | 订正后 rmse | Δrmse |
| --- | ---: | ---: | ---: | ---: | ---: |
| … | … | … | … | … | … |
```

（数字必须本次自算；禁止抄模板；禁止只留订正后一列。）

---

## 套用后自检（骨架外）

| 项 | 要求 |
| --- | --- |
| 对外签名 | 蓝色签名为 `XxxCli.call`，非模块 `process` |
| 示例数据 | 真实路径优先，否则自建写盘；禁止默认只读 `resource/cli_input` |
| 怎么跑 vs 示例 | 命令行只在「怎么跑」；使用示例不重复贴同套 bash |
| 输出 | 有方法数据结果展示（通常读 `output_path` 再 print）；不可只有 `call` 无结果 |
| 图 | 同要素须订正前+订正后；勿只贴输出；默认无差值/辅料多图；细节链插件页 |
| 检验 | 默认不加；要写则先调度再检验，CLI 写汇总+逐日；插件页另贴同一份汇总并链本页 |
| 页末 | 必须回链插件页 |
