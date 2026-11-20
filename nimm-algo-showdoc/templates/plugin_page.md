# 插件页套用模板

写/改插件页时：从下方「整页骨架」起**整段复制**到 ShowDoc，替换全部 `{{…}}`。  
勿从温度降尺度线上页抄示例数字、图与 RMSE。签名色值与 return 细则见 `../style.md`；示例/差值/框架图约束见 `../SKILL.md`。

占位符一览：`{{PACKAGE}}` `{{预报种类}}` `{{类别代码}}` `{{EntryA}}` `{{CLI_PAGE_URL}}` 等。

---

**基础信息**
- **所属包**: `{{PACKAGE}}`
- **预报类型**: {{预报种类_与算法清单一致}}
- **算法类别**: `{{类别代码}}`
- **正式目录规划**: `NIMM/{{类别代码}}/{{PACKAGE}}/`
- **对外入口**: `{{EntryA}}`、`{{EntryB_若有}}`
- **CLI 页**: [{{PACKAGE}}]({{CLI_PAGE_URL}})
- **应用场景**: [{{场景名}}]({{场景URL}})

{{一段话：做什么、单位、推荐步骤或衔接限制；细节见 CLI。无 CLI 则删「CLI 页」行并注明暂无独立 CLI 页。无应用场景则删该行。}}

**算法功能与流程**

```mermaid
flowchart LR
    IN[{{输入}}] --> E[{{EntryA}}]
    E --> OUT[{{输出}}]
```

1. {{用法与约束，非公式逐步推导}}
2. {{…}}

# {{EntryA}}

<!-- 签名：复制下面 div，只改内层文字；过长用 <br> 与 &nbsp; -->
<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">{{ClassName}}(<br>&nbsp;&nbsp;&nbsp;&nbsp;{{param=default}},<br>).process({{args}})</div></div>

{{原理短述；硬约束可一句附末。}}

**构造参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">{{name}}</span> | {{说明}} |

<!-- 无构造参数时仅保留一行：无 | 无额外构造参数 -->

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">{{name}}</span> | {{说明}} |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | {{类型如 xr.DataArray / tuple[…]；units；维度要点}} |

**使用示例**

{{引导句：域、分辨率、数据来源（真实优先 / 无则合成仅演示）、本节演示什么}}

```python
# 调用代码：读数 / 构造 / .process / print；关键步中文注释；发版正文禁本机绝对路径
```

```
{{方法数据结果展示：print(返回对象)；勿只打 name/shape}}
```

```python
# 画图代码（与调用分开）：中文图题先设 YaHei/SimHei
# 单场格点 pcolormesh_2d_grid；对照 creat_axs + add_contourf(..., cut_colorbar=False)
```

{{能画则：![图题](url)；同要素前后共用 clevs；差值规则见 SKILL}}

# {{EntryB_若有则整节复制；每入口仅一个使用示例、一条主路径}}

<!-- 可选：CLI 已有检验时，插件页只贴「一份」汇总表，并链到 CLI；默认不加 -->

## 检验结果

{{一句：相对何实况、窗口、订正前/后含义；Δrmse 负值=改善。逐日明细与调度见 CLI。}}

| 项目 | 订正前 | 订正后 |
| --- | ---: | ---: |
| mean_bias | **…** | **…** |
| mean_rmse | **…** | **…** |
| Δrmse | — | **…** |

完整检验（逐日表、调度说明）见 [{{PACKAGE}}]({{CLI_PAGE_URL}})。

---

算法 CLI 使用说明请见 [{{PACKAGE}}]({{CLI_PAGE_URL}})。

---

## 套用后自检（骨架外）

| 项 | 要求 |
| --- | --- |
| Mermaid | 须含入口类名；禁止「提取/积分/梯度→幂次」内部流水线 |
| return | 写清容器类型，非仅变量名 |
| 示例 | 真实样例优先，否则自建；禁「有输入−默认」差值；图题无「合成」；方法数据结果展示用无语言标记的代码围栏（不要 `text`） |
| 检验 | 默认不加；CLI 有检验时插件页可贴**同一份汇总表**（mean_bias / mean_rmse / Δrmse），**不**贴逐日表；文末链 CLI |
| 页末 | 有 CLI 则保留回链；无则按上文改基础信息 |
