# CLI 页套用模板

写/改 CLI 页时：从下方「整页骨架」起**整段复制**到 ShowDoc，替换全部 `{{…}}`。  
勿抄温度降尺度线上页的业务路径、检验数字与整套插件复刻图。有检验时**表式**对齐模板（订正前/后），数字须自算。约束见 `../SKILL.md` / `../style.md`。

---

**基础信息**
- **所属包**: `{{PACKAGE}}`
- **插件页**: [{{PACKAGE}}]({{PLUGIN_PAGE_URL}})
- **调度脚本**: `{{cli/xxx.py}}`

{{一段话：本页管 IO/调度；算法参数见插件页。本包以单次调用为主 / 或说明有批量。}}

**怎么跑**

（发版环境：本包已可导入。不要写「把 `00temp` 加入 PYTHONPATH」。）

```bash
python -m {{PACKAGE}}.cli
python -m {{PACKAGE}}.cli {{subcommand}}
# 无子命令分发、但脚本可当模块跑时，另列（示例）：
# python -m {{PACKAGE}}.cli.{{script_module}}
```

{{说明：无子命令时打印用法；带子命令进入对应 main；main 默认样例路径可一句带过，但不充当下方示例数据源。}}

<!-- 下表只列「可从命令行启动的入口」。禁止把 process 函数写成一行。
     三种常见形态：
     1) 有子命令：`python -m pkg.cli lapse-rate` → 表列子命令名；
     2) 无子命令、仅 `python -m pkg.cli` 打印用法：表可省略，或一行说明「只打印用法」；
     3) 另有 `python -m pkg.cli.xxx` 能直接跑脚本 __main__：应写入「怎么跑」代码块与表（脚本列 cli/xxx.py）。 -->

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| `{{有则填；无分发可写「无」或省略整表}}` | `{{cli/xxx.py}}` | {{做什么；可写 `python -m pkg.cli.xxx`}} |

# {{script_or_process_name}}

**调用插件**: `{{EntryName}}`

<!-- 签名 div：只改内层 -->
<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">process(<br>&nbsp;&nbsp;&nbsp;&nbsp;{{path_args}},<br>&nbsp;&nbsp;&nbsp;&nbsp;{{kw=default}},<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">{{name}}</span> | {{路径与调度含义}} |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | {{类型；output_path 非空时是否写 nc}} |

**使用示例**

{{引导句：与插件同域；真实样例路径优先，否则自建写盘；注明分辨率}}

```python
# 1) 场就绪（读真实样例或自建写 nc/JSON）；注释标明来源与分辨率
# 2) process(路径, …)
# 3) print(返回对象)；能画则 pcolormesh_2d_grid（中文图题先设 YaHei/SimHei）
# 贴图宜精简：通常 1–2 张结果场，勿整套复刻插件页多图
```

```
{{print(返回对象) 的 stdout；勿只打 name/shape}}
```

{{![结果图题](url) — 1～2 张即可}}

<!-- 多 CLI 入口则再复制一个 # 节 -->

# 批量调度示例

<!-- 无目录/多时次/runner 批处理则整节删除。有则保留；数据可用业务路径示意，不强制自建一批 nc。 -->

{{带注释的批处理代码；能画结果场则贴图}}

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
| 示例数据 | 真实路径优先，否则自建写盘；禁止默认只读 `resource/cli_input` |
| 输出 | 须有 print 返回场；stdout 用裸代码围栏（不要 `text` 语言标记）；不可只有调用代码 |
| 图 | 精简；细节对照链插件页 |
| 检验 | 默认不加；要写则先调度再检验，表含订正前/后与 Δrmse |
| 页末 | 必须回链插件页 |
