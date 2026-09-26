## 用途

本项目是「海洋探测建模与海底地形平台」的代码仓库，用于逐步实现该方向的建模与数据处理能力。

`ocean_sonar.crosspoint` 模块提供重叠测线交点精度评估能力，包括交点配对（`pair`）、多容差报告与门限判定（`gate`）以及二者的组合（`pair_gate`）。

## 环境与安装

- Python 3.11 及以上

```bash
python -m pip install -e .
```

## 测试

```bash
python -m pytest
```

## 命令行入口

安装后提供 `ocean-sonar-modeling` 命令：

```bash
ocean-sonar-modeling version    # 打印版本号
ocean-sonar-modeling --help     # 打印用法
```

### `render-trends TREND TREND [TREND ...]`

把多份 `serialize_trend` 生成的趋势 JSON 文件渲染为三行汇总文本。
路径按命令行顺序传入（至少两个），等价于调用
`ocean_sonar.crosspoint.render_trends(paths)`：成功时 stdout 输出其返回
的三行文本（`TRENDS=...`、`FILES=...`、`WORST=...`）加一个换行，stderr
为空，退出码 0；文件不存在、内容损坏等错误时 stdout 为空，stderr 输出
`ERROR <异常类名>: <异常消息>`，退出码 1；路径不足两个属于参数解析
错误，退出码 2。输入文件不会被修改。

```bash
ocean-sonar-modeling render-trends trend_a.json trend_b.json [trend_c.json ...]
```

### `export-trends TREND TREND [TREND ...] --output OUTPUT`

把多份 `serialize_trend` 生成的趋势 JSON 文件聚合后导出为一份报告
JSON。路径按命令行顺序传入（至少两个），等价于调用
`ocean_sonar.crosspoint.export_trends(paths, output)`：成功时静默
（stdout、stderr 均为空），退出码 0，并以 `"wb"` 覆写 `--output`
指定的文件；文件不存在、内容损坏等错误时 stdout 为空，stderr 输出
`ERROR <异常类名>: <异常消息>` 加换行，退出码 1；路径不足两个或缺少
`--output` 属于参数解析错误，退出码 2。输入趋势文件不会被修改。

```bash
ocean-sonar-modeling export-trends trend_a.json trend_b.json [trend_c.json ...] --output report.json
```

### `compare-reports REPORT REPORT [REPORT ...]`

把多份 `export-trends` 生成的趋势报告 JSON 依次比较并渲染为多行文本。
路径按命令行顺序传入（至少两个），等价于**仅调用一次**
`ocean_sonar.crosspoint.render_comparison(paths)`：成功时 stdout 输出其
返回文本加一个换行，stderr 为空，退出码 0；文件不存在、内容损坏等错误
时 stdout 为空，stderr 严格输出
`ERROR <异常类名>: <异常消息>` 加换行，退出码 1；路径不足两个属于参数
解析错误，退出码 2 且不调用业务函数。输入报告文件不会被修改。

```bash
ocean-sonar-modeling compare-reports report_a.json report_b.json [report_c.json ...]
```

### `export-comparison REPORT REPORT [REPORT ...] --output OUTPUT`

把多份 `export-trends` 生成的趋势报告 JSON 依次比较后导出为一份比较
结果 JSON。路径按命令行顺序传入（至少两个），等价于**仅调用一次**
`ocean_sonar.crosspoint.serialize_comparison(paths)` 得到字节串 `B`。
`--output` 不得与任一 REPORT 指向同一文件：双方都存在时用
`os.path.samefile` 识别软/硬链接，任一方不存在时比较
`os.path.normcase(os.path.realpath(os.path.abspath(path)))`；重合时抛出
`ValueError`。否则在 OUTPUT 同目录创建临时文件，写入 `B` 并
`flush()`、`os.fsync()` 后以 `os.replace` 原子替换 OUTPUT。成功时静默
（stdout、stderr 均为空），退出码 0；替换前发生失败会清除临时文件且既
有 OUTPUT 逐字节不变；文件不存在、内容损坏等其余错误不被包装，stdout
为空，stderr 严格输出 `ERROR <异常类名>: <异常消息>` 加换行，退出码
1；路径不足两个或缺少 `--output` 属于参数解析错误，退出码 2 且不调用
业务函数。REPORT 输入文件始终不被修改。

```bash
ocean-sonar-modeling export-comparison report_a.json report_b.json [report_c.json ...] --output comparison.json
```

### `audit-comparisons FILE FILE [FILE ...]`

把多份 `serialize_comparison` 生成的比较结果 JSON 汇总审计为一份紧凑
JSON。路径按命令行顺序传入（至少两个），等价于**仅调用一次**
`ocean_sonar.crosspoint.audit_comparisons(paths)`：成功时 stdout 以
`json.dumps(result, ensure_ascii=False, separators=(',', ':'),
allow_nan=False)` 输出其返回的 `dict` 并加一个换行，stderr 为空，退出码
0；文件不存在、内容损坏等错误时 stdout 为空，stderr 严格输出
`ERROR <异常类名>: <异常消息>` 加换行，退出码 1；路径不足两个属于参数
解析错误，退出码 2 且不调用业务函数。输入比较文件不会被修改。

```bash
ocean-sonar-modeling audit-comparisons comparison_a.json comparison_b.json [comparison_c.json ...]
```

### `export-audit FILE FILE [FILE ...] --output OUTPUT`

把多份 `serialize_comparison` 生成的比较结果 JSON 汇总审计后导出为一份
审计 JSON。路径按命令行顺序传入（至少两个），等价于**仅调用一次**
`ocean_sonar.crosspoint.export_audit(paths, output)`：成功时静默
（stdout、stderr 均为空），退出码 0，并以临时文件加 `os.replace`
原子覆写 `--output` 指定的文件；`--output` 不得与任一 FILE 指向同一
文件（双方都存在时用 `os.path.samefile` 识别软/硬链接，否则比较规范化
路径），重合时抛 `ValueError`；文件不存在、内容损坏等错误时 stdout 为
空，stderr 严格输出 `ERROR <异常类名>: <异常消息>` 加换行，退出码 1；
路径不足两个或缺少 `--output` 属于参数解析错误，退出码 2 且不调用业务
函数。输入比较文件不会被修改。

```bash
ocean-sonar-modeling export-audit comparison_a.json comparison_b.json [comparison_c.json ...] --output audit.json
```

### `render-audit AUDIT`

把一份 `serialize_audit`/`export-audit` 生成的审计 JSON 渲染为两行汇总
文本。等价于**仅调用一次** `ocean_sonar.crosspoint.render_audit(path)`：
成功时 stdout 输出其返回的两行文本（`AUDIT=...`、`WORST=...`）加一个
换行，stderr 为空，退出码 0；文件不存在、内容损坏等错误时 stdout 为空，
stderr 严格输出 `ERROR <异常类名>: <异常消息>` 加换行，退出码 1；参数
缺失或多余属于参数解析错误，退出码 2 且不调用业务函数。输入文件不会被
修改。

```bash
ocean-sonar-modeling render-audit audit.json
```

### `export-audit-report AUDIT --output OUTPUT`

把一份 `serialize_audit`/`export-audit` 生成的审计 JSON 序列化为审计报告
JSON 并写盘。等价于**仅调用一次**
`ocean_sonar.crosspoint.export_audit_report(audit_path, output)`：先且仅
调用一次 `serialize_audit_report(audit_path)` 得到字节串 `B`，其校验、异常
与文件不变性完全沿用且先于 `output` 生效；成功时静默（stdout、stderr 均为
空），退出码 0，并以临时文件加 `os.replace` 原子覆写 `--output` 指定的文
件；`--output` 必须为非空字符串且不得与 AUDIT 指向同一文件（双方都存在时
用 `os.path.samefile` 识别软/硬链接，否则比较规范化路径），非 `str`/空串
分别抛 `TypeError`/`ValueError`，重合抛 `ValueError`；文件不存在、内容损坏
等错误时 stdout 为空，stderr 严格输出
`ERROR <异常类名>: <异常消息>` 加换行，退出码 1；缺少 AUDIT、缺少
`--output` 或参数多余属于参数解析错误，退出码 2 且不调用业务函数。输入审
计文件不会被修改。

```bash
ocean-sonar-modeling export-audit-report audit.json --output audit_report.json
```

### `render-audit-report REPORT`

把一份 `serialize_audit_report`/`export-audit-report` 生成的审计报告 JSON
渲染为三行汇总文本。等价于**仅调用一次**
`ocean_sonar.crosspoint.render_audit_report(path)`：成功时 stdout 输出其
返回的三行文本（`REPORT=...`、`SUMMARY=...`、`WORST=...`）加一个换行，
stderr 为空，退出码 0；文件不存在、内容损坏等错误时 stdout 为空，stderr
严格输出 `ERROR <异常类名>: <异常消息>` 加换行，退出码 1；参数缺失或多余
属于参数解析错误，退出码 2 且不调用业务函数。输入文件不会被修改。

```bash
ocean-sonar-modeling render-audit-report audit_report.json
```

## Python 接口

包 `ocean_sonar` 的 `__version__` 为当前版本号。

交点相关接口位于 `ocean_sonar.crosspoint`，该模块导出：
`evaluate`、`report`、`pair`、`audit`、`profile`、`aggregate`、
`dashboard`、`dashboard_summary`、`dashboard_report`、`gate`、
`gate_report`、`pair_gate`、`pair_gate_report`、`pair_gate_score`、
`pair_gate_score_report`、`pair_gate_score_summary`、
`pair_gate_quality`、`pair_gate_quality_report`、
`render_quality_batch`、`serialize_quality_batch`、
`load_quality_batch`、`aggregate_quality_batches`、
`dump_aggregate`、`load_aggregate`、`trend`、
`serialize_trend`、`render_trend`、`load_trend`、
`load_trends`、`render_trends`、`export_trends`、
`load_trend_report`、
`serialize_comparison`、`render_comparison`、`load_comparison`、
`audit_comparisons`、`export_audit`、`render_audit`、
`serialize_audit_report`、`load_audit_report`、
`export_audit_report`、`render_audit_report`、
`serialize_pair_gate_score_summary`、`render_pair_gate_score_summary`、
`load_pair_gate_score_summary`。

### 通用约定

- 容器类型只接受 `list` 或 `tuple`；布尔值（`bool`）不被视为数值。
- 类型不符抛出 `TypeError`；容器为空、元素个数不符、数值非有限
  （`inf`/`nan`）或取值越界等其他校验失败抛出 `ValueError`。
- 所有校验按“先报错者胜出”的固定顺序进行（见各函数说明）。
- 数值统计与点坐标一律经 `round(float(value), 6)` 保留 6 位小数；
  舍入结果为负零的一律归一化为 `0.0`。
- 所有函数都不修改输入参数。

### `pair(first, second, tolerance=1.0)`

把两条测线在同一位置附近的观测点配成交点。

**参数：**

- `first`、`second`：非空 `list`/`tuple`，元素为点；每个点是恰好 3 个
  元素的 `list`/`tuple` `(x, y, d)`，各字段为有限的、非布尔的
  `int`/`float`，且 `d >= 0`。
- `tolerance`：有限的、非布尔的 `int`/`float`，且 `> 0`；默认 `1.0`。

**配对规则：** 按输入顺序逐个处理 `first` 中的点，在尚未被使用的
`second` 点中选取未舍入二维距离
`sqrt((x1 - x2)**2 + (y1 - y2)**2)` 最小者，且该距离必须
`<= tolerance`；距离相等时取输入顺序中最靠前的 `second` 点。找不到
合格匹配的 `first` 点被跳过；每个 `second` 点至多使用一次。若最终一个
交点都没有形成，抛出 `ValueError("no points matched within tolerance")`。

**校验顺序（先报错者胜出）：**

1. `first` 容器类型（`TypeError: first must be a list or tuple`）；
2. `first` 非空（`ValueError: first must be non-empty`）；
3. `second` 容器类型（`TypeError: second must be a list or tuple`）；
4. `second` 非空（`ValueError: second must be non-empty`）；
5. 按下标顺序逐点校验：先校验全部 `first` 点，再校验全部 `second`
   点。每个点依次校验：点容器类型（`must be a list or tuple`）、
   元素个数（`must have 3 elements`）、`x`/`y`/`d` 三个字段的类型
   （`<name> must be a non-bool int or float`）、三个字段的有限性
   （`<name> must be finite`）、最后 `d >= 0`（`d must be >= 0`）；
6. 最后校验 `tolerance`：类型（`tolerance must be a non-bool int or
   float`）、有限性（`tolerance must be finite`）、正值性
   （`tolerance must be > 0`）。

点级错误信息分别带 `first[i]: ` 或 `second[j]: ` 前缀。

**返回：** 一个 `tuple`，按 `first` 输入顺序排列，元素为四元组
`(x, y, d1, d2)`，四个值均为 `float`：`x`/`y`/`d1` 取自 `first` 点，
`d2` 取自匹配上的 `second` 点。各值按通用约定舍入到 6 位小数（负零
归一化为 `0.0`）。

### `gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0)`

对多容差交点汇总报告执行门限判定。

**参数：**

- `crossings`：非空 `list`/`tuple`，元素为恰好 4 个元素的
  `list`/`tuple` `(x, y, d1, d2)`，各字段为有限的、非布尔的
  `int`/`float`，且 `d1 >= 0`、`d2 >= 0`。
- `tolerances`：非空 `list`/`tuple`，元素为有限的、非布尔的
  `int`/`float`，且 `> 0`。
- `min_mean_ratio`：有限的、非布尔的 `int`/`float`，取值在
  `[0, 1]`；默认 `1.0`。
- `max_rmse_limit`：有限的、非布尔的 `int`/`float`，且 `>= 0`；
  默认 `1.0`。

**校验顺序（先报错者胜出）：** 先完整校验 `crossings`（容器类型
`crossings must be a list or tuple`、非空 `crossings must be non-empty`、
再按下标逐点校验：点容器类型、4 元素个数、`x`/`y`/`d1`/`d2` 字段
类型、字段有限性、`d1 >= 0`、`d2 >= 0`），然后校验 `tolerances`
（容器类型 `tolerances must be a list or tuple`、非空
`tolerances must be non-empty`、再按下标逐个校验类型、有限性、
`> 0`），最后才依次校验两个门限参数：`min_mean_ratio` 的类型、有限性、
`[0, 1]` 取值（`min_mean_ratio must be a non-bool int or float` /
`min_mean_ratio must be finite` / `min_mean_ratio must be in [0, 1]`），
随后是 `max_rmse_limit` 的类型、有限性、非负性
（`max_rmse_limit must be a non-bool int or float` /
`max_rmse_limit must be finite` / `max_rmse_limit must be >= 0`）。
点级与容差级错误分别带 `crossings[i]: ` 或 `tolerances[i]: ` 前缀。

**返回：** 键序为 `report, checks, quality` 的 `dict`：

- `report`：`dashboard_report(crossings, tolerances)` 返回的原 `dict`
  （键序 `dashboard, summary, quality`），不做修改。其中 `summary` 的
  键序为 `count, pass_count, fail_count, total_count, mean_bias,
  max_rmse, mean_ratio, best_tolerance, quality_score`；计数为 `int`，
  `best_tolerance` 为 `float` 或 `None`，其余统计量为按通用约定舍入到
  6 位小数的 `float`（负零归一化为 `0.0`）。
- `checks`：键序为 `mean_ratio, max_rmse, within_ok, rmse_ok` 的
  `dict`。前两个值为取自 `report["summary"]` 的 `float`，保持不变；
  后两个为 `bool`，分别是
  `summary["mean_ratio"] >= min_mean_ratio` 和
  `summary["max_rmse"] <= max_rmse_limit`。
- `quality`：仅当 `report["quality"] == "pass"` 且 `within_ok`、
  `rmse_ok` 均为真时为 `"pass"`，否则为 `"fail"`。

### `pair_gate(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0)`

先配对、再门限的组合接口。

执行时**先且仅调用一次** `pair(first, second, match_tolerance)`，得到
交点元组 `P`；然后**仅调用一次**
`gate(P, tolerances, min_mean_ratio, max_rmse_limit)`，得到 `G`。
因此校验顺序即两阶段之和：`pair` 的全部校验（含 `first`/`second` 点与
`match_tolerance`）先发生，其后才是 `gate` 对 `crossings`、`tolerances`
及两个门限参数的校验；任何异常都原样向上传播，不在此函数内包装或替换。
输入参数不被修改，也不被复制改写。

**返回：** 键序为 `pairs, report, quality` 的 `dict`：

- `pairs`：`pair` 返回的原 `tuple` `P`（即 `G` 所评估的交点）；
- `report`：`gate` 返回的原 `dict` `G`；
- `quality`：即 `G["quality"]`，取值 `"pass"` 或 `"fail"`。

### `pair_gate_report(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0)`

在 `pair_gate` 结果上补充配对覆盖率汇总。

执行时**仅调用一次** `pair_gate(first, second, tolerances,
match_tolerance, min_mean_ratio, max_rmse_limit)`，因此其全部校验顺序、
异常（原样向上传播）与下标前缀规则在此同样适用。输入参数与
`pair_gate` 的返回结果均不被修改。

记 `G` 为 `pair_gate` 返回的原 `dict`，`P = G["pairs"]`，
`m = len(P)`，`f = len(first)`，`s = len(second)`。

**返回：** 键序为 `pair_gate, matching, quality` 的 `dict`：

- `pair_gate`：`pair_gate` 返回的原 `dict` `G`，不做修改；
- `matching`：键序为 `matched, first_total, second_total,
  first_coverage, second_coverage` 的 `dict`。前三项为 `int`，分别是
  `m`、`f`、`s`；后两项为 `float`，分别是 `round(m / f, 6)` 和
  `round(m / s, 6)`（负零归一化为 `0.0`）；
- `quality`：仅当 `G["quality"] == "pass"` 且两个覆盖率均为 `1.0`
  时为 `"pass"`，否则为 `"fail"`。

### `pair_gate_score(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0)`

在 `pair_gate_report` 结果上计算综合得分。

执行时**仅调用一次** `pair_gate_report(first, second, tolerances,
match_tolerance, min_mean_ratio, max_rmse_limit)`，因此其全部校验顺序、
异常（原样向上传播）与下标前缀规则在此同样适用。输入参数与
`pair_gate_report` 的返回结果均不被修改。

记 `R` 为 `pair_gate_report` 返回的原 `dict`，
`G = R["pair_gate"]`，`M = R["matching"]`，
`S = G["report"]["report"]["summary"]`（即 `gate` 结果内嵌的
`dashboard_report` 汇总）。

**返回：** 键序为 `pair_gate, matching, score, quality` 的 `dict`：

- `pair_gate`：即 `G` 本身，不做修改；
- `matching`：即 `M` 本身，不做修改；
- `score`：`float`，为
  `round(100 * M["first_coverage"] * M["second_coverage"] *
  S["mean_ratio"], 6)`（负零归一化为 `0.0`）；
- `quality`：仅当 `R["quality"] == "pass"` 且 `score == 100.0` 时为
  `"pass"`，否则为 `"fail"`。

### `pair_gate_score_report(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0)`

在 `pair_gate_score` 结果上补充覆盖率与得分裕量。仅调用一次
`pair_gate_score(...)`，校验顺序、异常（原样向上传播）与下标前缀规则
同样适用，输入与其返回结果均不被修改。

返回键序为 `score_report, metrics, quality` 的 `dict`：`score_report`
为 `pair_gate_score` 返回的原 `dict`；`metrics` 键序为
`coverage_product, score_margin`，分别为
`round(first_coverage * second_coverage, 6)` 与
`round(100 - score, 6)`（均为负零归一化的 `float`）；`quality` 仅当
原 `quality == "pass"` 且 `score_margin == 0.0` 时为 `"pass"`。

### `pair_gate_score_summary(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0)`

把 `pair_gate_score_report` 的结果压成一个扁平汇总。仅调用一次
`pair_gate_score_report(...)`，校验顺序、异常（原样向上传播）与下标
前缀规则同样适用，输入与其返回结果均不被修改。

返回键序为 `score_report, summary, quality` 的 `dict`：`score_report`
为原 `dict`；`summary` 键序为 `coverage_product, score_margin,
matched, pair_quality`，其中前两个为取自 `metrics` 的 `float`、
`matched` 为 `int`（匹配对数）、`pair_quality` 为 `str`（内层
`pair_gate` 的质量），全部原样复制不重算；`quality` 仅当原
`quality` 与 `pair_quality` 均为 `"pass"` 且 `score_margin == 0.0`
时为 `"pass"`。

### `render_pair_gate_score_summary(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0) -> str`

把 `pair_gate_score_summary` 的结果渲染成三行文本。

执行时**仅调用一次** `pair_gate_score_summary(first, second,
tolerances, match_tolerance, min_mean_ratio, max_rmse_limit)`，因此其
全部校验顺序、异常（原样向上传播）与下标前缀规则在此同样适用。输入
参数与其返回结果均不被修改。

记 `R` 为 `pair_gate_score_summary` 返回的 `dict`，返回三行、以
`\n` 连接且**无尾换行**的 `str`：

```text
QUALITY=<R["quality"]>
SUMMARY=coverage_product=<R["summary"]["coverage_product"]>;score_margin=<R["summary"]["score_margin"]>;matched=<R["summary"]["matched"]>;pair_quality=<R["summary"]["pair_quality"]>
REPORT=first_coverage=<R["score_report"]["score_report"]["matching"]["first_coverage"]>;second_coverage=<R["score_report"]["score_report"]["matching"]["second_coverage"]>;score=<R["score_report"]["score_report"]["score"]>
```

其中内层 `score_report` 即 `pair_gate_score` 返回的 `dict`。

格式化规则：`float` 一律使用 `format(v, ".6f")`（负零渲染为
`0.000000`），`int` 以十进制输出，`str` 原样插入。

### `dump_aggregate(paths) -> bytes`

把 `aggregate_quality_batches` 的聚合结果编码为 JSON 字节串。

执行时**仅调用一次** `aggregate_quality_batches(paths)`，因此其全部
校验顺序、异常（原样向上传播）与下标前缀规则在此同样适用；输入不被
修改。

记 `A` 为其返回的 `dict`，编码对象即 `A` 本身：顶层键序保持
`batches, summary, quality`，所有值原样保留；唯一的结构转换是把
tuple（顶层 `batches`）递归编码为 JSON 数组，各
`batch["records"]` 仍为数组，其余容器仍为对象或数组。

编码规范与 `serialize_quality_batch` 一致：UTF-8 JSON，
`ensure_ascii=False`、`separators=(",", ":")`、`allow_nan=False`，
无缩进、无尾换行；聚合结果中的浮点数均已按
`round(float(v), 6)` 保留 6 位小数并将负零归一化为 `0.0`。任何
JSON 或 UTF-8 编码失败抛出 `ValueError`。返回 `bytes`。

### `load_aggregate(path) -> dict`

从文件读回 `dump_aggregate` 生成的 JSON 聚合结果。

`path` 必须为非空 `str`：非 `str` 抛 `TypeError`，空串抛
`ValueError`。文件以二进制模式（`"rb"`）打开并整体读出；文件不存在
抛 `FileNotFoundError`，路径为目录抛 `IsADirectoryError`，其余
`OSError` 原样传播。文件不被修改。

字节必须与 `dump_aggregate` 对同一值的输出完全一致：紧凑 UTF-8
JSON，无 BOM、无尾换行；BOM、尾换行、UTF-8 解码失败或 JSON 解析
失败均抛 `ValueError`，`NaN`/`Infinity` 等非常量 token 一律拒绝。

解码值必须是顶层键序恰为 `batches, summary, quality` 的对象：
`batches` 为非空数组，各项键序恰为 `index, path, batch`，其中
`index` 为从 0 连续的非布尔 `int`，`path` 为非空 `str`，`batch`
满足 `load_quality_batch` 返回结构的全部规则；`summary` 键序恰为
`batch_count, record_count, mean_coverage, mean_score,
worst_batch_index, worst_record_index, quality`。按各 batch 的
`records` 原序重算：批次与记录计数、`fsum` 均值（6 位小数舍入、负零
归一化）、按 `(score, coverage, 批次索引, 记录 index)` 字典序最小的
最差位置，以及质量判定，并与 `summary` 及顶层 `quality` 逐项相等。
文件字节还必须与解码值的规范重编码逐字节相等；任何键序、类型、范围、
关系、解析或规范字节不匹配均抛 `ValueError`。

返回保持原键序的 `dict`：仅顶层 `batches` 数组还原为 tuple，各
`batch["records"]` 保持 list，其余容器保持 dict/list。文件不被修改。

### `trend(paths) -> dict`

沿同一组批次的多份聚合快照逐份比较变化趋势。

`paths` 必须为至少含 2 项的 list/tuple；各项按下标顺序校验为非空
`str`。校验顺序（先报错者胜出）：`paths` 容器、项数、再逐项（类型、
非空）。容器非 list/tuple 或某项非 `str` 抛 `TypeError`；少于 2 项或
空串抛 `ValueError`。项错误前缀为 `paths[i]: `。

随后按输入顺序对每个 path **仅调用一次** `load_aggregate`；其异常原样
传播。输入与文件均不被修改。

各份聚合结果必须与首份批次数相同，且对应批次 `b` 的 `path` 与
`records` 条数相同，否则抛 `ValueError`。

对 `i = 1..n-1`、批次 `b`、记录 `r`，以原始 float 计算
`dc = coverage_i - coverage_(i-1)`、
`ds = score_i - score_(i-1)`；`dc < 0`、`ds < 0` 或 quality 由
`pass` 变 `fail` 即视为退化。记 `K` 为比较总数，`w` 为按**未舍入**
元组 `(ds, dc, i, b, r)` 字典序最小的比较；不排序、不复制、不增补。

返回键序为
`count, changes, degraded, coverage_delta, score_delta, worst, quality`
的 `dict`：`count` 为快照数 `n`，`changes` 为 `K`，`degraded` 为退化
比较数，三者均为 `int`；两个 delta 分别为全部 `dc`/`ds` 经
`math.fsum` 求和后除以 `K` 的 float；`worst` 为
`(i, b, r, dc, ds)`，前三项为 `int`、后两项为 float；所有 float 均经
`round(float(v), 6)` 且负零归一化为 `0.0`。`quality` 仅在无退化时为
`pass`，否则为 `fail`。

### `serialize_trend(paths) -> bytes`

把 `trend` 的结果编码为 JSON 字节串。

执行时**仅调用一次** `trend(paths)`，因此其全部校验顺序、异常（原样
向上传播）与 `paths[i]: ` 前缀规则在此同样适用；输入与文件均不被
修改。

记 `T` 为 `trend(paths)` 的返回值，编码对象键序恰为
`count, changes, degraded, coverage_delta, score_delta, worst,
quality`：前三项取 `T` 中对应的 `int`，两个 delta 取对应的 float，
`worst` 元组编码为五项 JSON 数组 `[i, b, r, dc, ds]`，`quality` 原样
取值；不重算、不排序、不增加键。

编码为 UTF-8 JSON，`ensure_ascii=False`、
`separators=(",", ":")`、`allow_nan=False`，无 BOM、无尾换行；float
先经 `round(float(v), 6)` 并将负零归一化为 `0.0`，`int` 以十进制
输出，`str` 原样插入。任何 JSON 或 UTF-8 编码失败抛出 `ValueError`。
返回 `bytes`。

### `render_trend(paths) -> str`

把 `trend` 结果渲染为两行文本。

执行时**仅调用一次** `trend(paths)`，因此其全部校验顺序、异常（原样
向上传播）与 `paths[i]: ` 前缀规则在此同样适用；输入与文件均不被
修改。

记 `T` 为 `trend(paths)` 的返回值、
`(i, b, r, dc, ds) = T["worst"]`，返回以 `\n` 连接、无尾换行的两
行：

```
TREND=<count>,<changes>,<degraded>,<coverage_delta>,<score_delta>,<quality>
WORST=<i>,<b>,<r>,<dc>,<ds>
```

各值依次直接取自 `T` 与 `T["worst"]`，不重算、不排序：`int` 以十
进制输出，`str` 原样插入，float 使用 `format(v, ".6f")`（负零渲染
为 `0.000000`）。

### `load_trend(path) -> dict`

从文件读回 `serialize_trend` 生成的 JSON 趋势结果。

`path` 必须为非空 `str`：非 `str` 抛 `TypeError`，空串抛
`ValueError`。文件以二进制模式（`"rb"`）打开并整体读出；文件不存在
抛 `FileNotFoundError`，路径为目录抛 `IsADirectoryError`，其余
`OSError` 原样传播。文件不被修改。

字节必须与 `serialize_trend` 对同一值的输出完全一致：无 BOM、无尾
换行的紧凑 UTF-8 JSON；BOM、尾换行、UTF-8 解码失败、JSON 解析失败、
`NaN`/`Infinity` 等非常量 token 或重复键均抛 `ValueError`。

解码值必须是键序恰为
`count, changes, degraded, coverage_delta, score_delta, worst,
quality` 的对象，缺失、额外键或键序错误均抛 `ValueError`。前三项为
非布尔 `int`：`count >= 2`、`changes > 0`、
`degraded ∈ [0, changes]`；两个 delta 为有限非布尔 float，
`coverage_delta ∈ [-1, 1]`、`score_delta ∈ [-100, 100]`。
`worst` 为五元素数组 `[i, b, r, dc, ds]`：前三项为非布尔 `int` 且
`1 ≤ i < count`、`b`/`r >= 0`，后两项为有限非布尔 float，范围分别
同两个 delta。所有 float 必须等于 `round(float(v), 6)` 且禁用负零；
`quality` 仅取 `pass`/`fail`，且当且仅当 `degraded = 0` 时为
`pass`。文件字节还必须与解码值的规范重编码逐字节相等；任何类型、
范围、关系或规范字节不匹配均抛 `ValueError`。

返回保持原键序的 `dict`：仅 `worst` 数组还原为 tuple，其余值原样
返回。文件不被修改。

### `load_trends(path) -> dict`

从文件读回 `dump_trends` 生成的 JSON 多文件趋势汇总结果；`path`
校验、`"rb"` 读取与系统异常（文件不存在抛 `FileNotFoundError`、
路径为目录抛 `IsADirectoryError`、其余 `OSError` 原样传播）、BOM 与
尾换行拒绝、UTF-8/JSON/`NaN`/`Infinity`/重复键处理、规范重编码逐字节
核对及文件不变性，规则与 `load_trend` 完全一致。

解码值必须是键序恰为
`file_count, changes, degraded, coverage_delta, score_delta, worst,
quality` 的对象，重复、缺失、额外键或键序错误均抛 `ValueError`。前三
项为非布尔 `int`：`file_count >= 2`、`changes > 0`、
`degraded ∈ [0, changes]`；两个 delta 为有限非布尔 float，
`coverage_delta ∈ [-1, 1]`、`score_delta ∈ [-100, 100]`。
`worst` 为六元素数组 `[j, i, b, r, dc, ds]`：前四项为非布尔 `int`
且 `0 ≤ j < file_count`、`i >= 1`、`b`/`r >= 0`；`dc`/`ds` 为有限
非布尔 float，范围分别同两个 delta。所有 float 必须等于
`round(float(v), 6)` 且禁用负零；`quality` 仅取 `pass`/`fail`，且当
且仅当 `degraded = 0` 时为 `pass`。文件字节还必须与解码值的规范重
编码逐字节相等；任何解析、键序、类型、范围、关系或规范字节不匹配均
抛 `ValueError`。

返回保持原键序的 `dict`：仅 `worst` 数组还原为 tuple，其余值原样
返回。文件不被修改。

### `render_trends(paths) -> str`

把多文件趋势汇总结果连同逐文件贡献渲染为三行文本。

执行时**仅调用一次** `aggregate_trends(paths)` 得到 `A`，并按输入
顺序对每个 path **仅调用一次** `load_trend(path)` 得到 `T_j`，不调
用其他组合或读取函数；因此路径校验与异常（原样向上传播）和
`aggregate_trends` 完全一致，`paths[i]: ` 前缀规则同样适用。输入与
文件均不被修改。

记 `K = A["changes"]`，对每个文件 `j` 及
`x ∈ {coverage_delta, score_delta}`，以原始 float 计算变化量加权占比

```
p(j, x) = T_j[x] * T_j["changes"] / K
u(x)    = sqrt(fsum(T_j["changes"] * (T_j[x] - A[x]) ** 2) / K)
```

（离散度中的均值即 `A[x]` 本身。）每个 `p`、`u` 经
`round(float(v), 6)` 舍入，负零归一化为 `0.0`。最差文件下标 `w`
取使**未舍入**三元组
`(p(j, score_delta), p(j, coverage_delta), j)` 字典序最小者。

返回以 `\n` 连接、无尾换行的三行：

```
TRENDS=<file_count>,<changes>,<degraded>,<coverage_delta>,<score_delta>,<quality>
FILES=<j>:<覆盖p>:<得分p>|...;RMSE=<覆盖u>,<得分u>;WORST_FILE=<w>
WORST=<j>,<i>,<b>,<r>,<dc>,<ds>
```

TRENDS 行各值直接取自 `A`；FILES 行按 `j` 顺序以 `|` 连接各
`<j>:<覆盖p>:<得分p>`（占比为已舍入值），随后追加
`;RMSE=<覆盖u>,<得分u>;WORST_FILE=<w>`；WORST 行六项直接取自
`A["worst"]`，不重算、不排序。格式化规则：`int` 以十进制输出，
`str` 原样插入，`float` 使用 `format(v, ".6f")`（负零渲染为
`0.000000`）。

### `export_trends(paths, output) -> bytes`

聚合多份趋势文件并导出为报告 JSON，同时写盘并返回所写字节。

执行时**先且仅调用一次** `aggregate_trends(paths)` 得到 `A`，在此
之前不做任何其他工作、之后也不再调用第二次；因此 `paths` 的校验
契约（容器、至少 2 项、逐项非空 `str`，错误前缀 `paths[i]: `）与
异常（原样向上传播）完全沿用 `aggregate_trends`，且 `paths` 的错误
先于 `output` 报出。随后才校验 `output`：必须为非空 `str`——非
`str` 抛 `TypeError`（`output must be a str`），空串抛
`ValueError`（`output must not be empty`）。输入与文件均不被修改。

编码对象顶层键序恰为 `sources, summary`：`sources` 为 `paths` 原序
字符串的 JSON 数组（不排序、不去重）；`summary` 即 `A` 本身，键序
`file_count, changes, degraded, coverage_delta, score_delta, worst,
quality`，其 `worst` tuple 编码为六项 JSON 数组。JSON 编码规范与
`dump_trends` 完全一致：UTF-8、`ensure_ascii=False`、
`separators=(",", ":")`、`allow_nan=False`，无缩进、无 BOM、无尾
换行，float 经 `round(float(v), 6)` 并将负零归一化为 `0.0`；任何
JSON 或 UTF-8 编码失败抛 `ValueError`。

仅在编码完成后，才以 `"wb"` 打开并覆写 `output`，写入上述字节。
返回值与写入文件的字节为同一份 `bytes`。

### `load_trend_report(path) -> dict`

从文件读回 `export_trends` 生成的 JSON 趋势报告。

`path` 的非空 `str` 校验、`"rb"` 整体读取与系统异常（文件不存在抛
`FileNotFoundError`、路径为目录抛 `IsADirectoryError`、其余
`OSError` 原样传播）、BOM 与尾换行拒绝、UTF-8/JSON 解码、
`NaN`/`Infinity` 与重复键拒绝、规范重编码逐字节核对等规则，全部
沿用 `load_trends`；任何解析、解码或规范字节不匹配均抛
`ValueError`。文件不被修改。

解码值必须是顶层键序恰为 `sources, summary` 的对象，重复、缺失、
额外键或键序错误均抛 `ValueError`。`sources` 必须是至少含 2 项的
数组，且每项均为非空 `str`（类型不符为 `TypeError`、项数不足或空
串为 `ValueError`，最终统一包成 `ValueError`）。`summary` 必须满足
`load_trends` 返回结构的全部契约（键序
`file_count, changes, degraded, coverage_delta, score_delta, worst,
quality` 及其类型、范围、关系与规范字节规则），并且其
`file_count` 必须等于 `sources` 的长度，否则抛 `ValueError`。

返回保持 `sources, summary` 键序的 `dict`：`sources` 为按存储顺序
排列的路径字符串 list，`summary` 中仅 `worst` 还原为 tuple（与
`load_trends` 一致），其余值原样返回。文件不被修改。

### `serialize_comparison(paths) -> bytes`

把 `compare_reports` 的比较结果编码为 JSON 字节串。

执行时**仅调用一次** `compare_reports(paths)`，因此其全部校验顺序、
异常（原样向上传播）与 `paths[i]: ` 前缀规则在此同样适用；输入与
文件均不被修改。

记 `C` 为其返回的 `dict`，编码对象保持 `C` 的原键序与原值：顶层键序
为 `changes, worst, quality`；唯一的结构转换是把 `changes` 元组编码为
JSON 数组，各变化项与 `worst` 仍保持
`index, degraded_delta, coverage_delta, score_delta, quality` 键序。

编码规范与 `dump_trends` 一致：UTF-8 JSON，`ensure_ascii=False`、
`separators=(",", ":")`、`allow_nan=False`，无缩进、无 BOM、无尾
换行；float 先经 `round(float(v), 6)` 并将负零归一化为 `0.0`，`int`
以十进制输出，`str` 原样插入。任何 JSON 或 UTF-8 编码失败抛出
`ValueError`。返回 `bytes`。

### `render_comparison(paths) -> str`

把 `compare_reports` 的比较结果渲染为多行文本。

执行时**仅调用一次** `compare_reports(paths)`，因此其全部校验顺序、
异常（原样向上传播）与 `paths[i]: ` 前缀规则在此同样适用；输入与
文件均不被修改。

记 `C` 为其返回的 `dict`、`n = len(C["changes"])`，返回以 `\n` 连接、
无尾换行的文本：

```
QUALITY=<quality>;COUNT=<n>;WORST_INDEX=<index>
CHANGE[<index>]=<degraded_delta>,<coverage_delta>,<score_delta>,<quality>
...
```

首行各值依次取 `C["quality"]`、`n` 与 `C["worst"]["index"]`；其后按
`C["changes"]` 原序逐项输出一行 `CHANGE[...]`，各值直接取自对应的
变化项，不重算、不排序。格式化规则：`int` 以十进制输出，`str` 原样
插入，`float` 使用 `format(v, ".6f")`（负零渲染为 `0.000000`）。

### `load_comparison(path) -> dict`

从文件读回 `serialize_comparison` 生成的 JSON 比较结果。

`path` 必须是非空 `str`：非 `str` 抛 `TypeError`，空串抛
`ValueError`。文件以 `"rb"` 整体读取；文件不存在抛
`FileNotFoundError`，路径为目录抛 `IsADirectoryError`，其余
`OSError` 原样传播。文件不被修改。

文件字节必须恰为 `serialize_comparison` 对同一值生成的字节：
紧凑 UTF-8 JSON（`ensure_ascii=False`、`separators=(",", ":")`、
`allow_nan=False`），无 BOM、无尾换行。BOM、尾换行、UTF-8 解码
失败或 JSON 解析失败均抛 `ValueError`；`NaN`/`Infinity` 常量、
其他非有限 token 与重复对象键一律拒绝。

解码值必须是顶层键序恰为 `changes, worst, quality` 的对象——
重复、缺失、额外键或键序错误均抛 `ValueError`。`changes` 必须是
非空数组，各项键序恰为
`index, degraded_delta, coverage_delta, score_delta, quality`：
`index` 与 `degraded_delta` 为非 bool `int`，`index` 从 `1`
起连续，`degraded_delta` 属 `[-2, 2]`；`coverage_delta` 与
`score_delta` 为有限非 bool `float`，依次属 `[-2, 2]`、
`[-200, 200]`，且各自等于 `round(float(v), 6)`、禁负零；
`quality` 仅取 `"pass"`/`"fail"`。`worst` 键序相同，且必须与
某个 `changes` 项逐字段相等。顶层 `quality` 仅当全部项均为
`"pass"` 时为 `"pass"`，否则为 `"fail"`。文件字节还须与解码值
的规范重编码逐字节一致；任何键序、类型、范围、连续性、关系或
规范字节不匹配均抛 `ValueError`。

返回保持上述键序的 `dict`：仅 `changes` 数组还原为 `tuple`
（其 `worst` 项即命中的那一元组项），其余值原样返回。文件
不被修改。

### `audit_comparisons(paths) -> dict`

汇总审计多份 `serialize_comparison` 生成的比较结果 JSON 文件。

`paths` 的输入契约完全沿用 `compare_reports`：必须为至少含 2 项的
list/tuple；各项按下标顺序校验为非空 `str`。校验顺序（先报错者胜
出）：`paths` 容器、项数、再逐项（类型、非空）。容器非 list/tuple
或某项非 `str` 抛 `TypeError`；少于 2 项或空串抛 `ValueError`。项错
误前缀为 `paths[i]: `。

随后按输入顺序对每个 path **仅调用一次** `load_comparison`；其异常
原样传播。输入与文件均不被修改。

各份比较结果按文件顺序、并在每份文件内按 `changes` 原序展开；不排
序、不去重、不增补。记展开总项数为 `K`、其中 `quality` 为 `"fail"`
的项数为 `E`，最差项取使元组
`(score_delta, coverage_delta, -degraded_delta, 文件下标, index)`
字典序最小的项（各值均为 `load_comparison` 读回的原值，不重算、不
重新舍入）。

返回键序为 `files, changes, failed, worst, quality` 的 `dict`：
`files` 为文件数，`changes` 为 `K`，`failed` 为 `E`，三者均为
`int`；`worst` 为六元 tuple
`(文件下标, index, degraded_delta, coverage_delta, score_delta,
quality)`，其中文件下标、`index`、`degraded_delta` 为 `int`，
`coverage_delta`、`score_delta` 为 `float`，`quality` 为对应项原样
的 `"pass"`/`"fail"` 字符串。`quality` 仅在 `E = 0` 时为 `"pass"`，
否则为 `"fail"`。

### `export_audit(paths, output) -> bytes`

把多份比较结果 JSON 的审计结果序列化后原子写盘，并返回所写字节。

执行时**先且仅调用一次** `serialize_audit(paths)` 得到字节串 `B`，在
此之前不做任何其他工作、之后也不再调用第二次；因此 `paths` 的校验契约
（容器、至少 2 项、逐项非空 `str`，错误前缀 `paths[i]: `）与异常（原
样向上传播）完全沿用 `serialize_audit`，且 `paths` 的错误先于 `output`
报出。输入与文件均不被修改。

随后才校验 `output`：必须为非空 `str`——非 `str` 抛 `TypeError`
（`output must be a str`），空串抛 `ValueError`
（`output must not be empty`）。

`output` 不得与任一 `paths` 项指向同一文件：双方都存在时用
`os.path.samefile` 识别软/硬链接，任一方不存在时比较
`os.path.normcase(os.path.realpath(os.path.abspath(path)))`；重合时抛
`ValueError`。

非重合时在 `output` 同目录创建临时文件，以二进制写入 `B`，`flush()`、
`os.fsync()` 后用 `os.replace` 原子替换 `output`。替换前发生失败会清除
临时文件且既有 `output` 逐字节不变；`OSError` 原样传播。返回值与写入
文件的字节为同一份 `bytes`。

### `render_audit(path) -> str`

把一份审计 JSON 渲染为两行汇总文本。

执行时**仅调用一次** `load_audit(path)` 得到 `A`，不调用任何其他加载或
汇总函数；因此 `path` 的校验契约与异常完全沿用 `load_audit`：非 `str`
抛 `TypeError`，空串抛 `ValueError`，文件缺失抛 `FileNotFoundError`，
目录抛 `IsADirectoryError`，其余 `OSError` 原样传播，解析、结构或规范
字节非法抛 `ValueError`。输入文件不会被修改。

返回以 `\n` 连接、无尾换行的两行：

```
AUDIT=<files>,<changes>,<failed>,<quality>
WORST=<file_index>,<index>,<degraded_delta>,<coverage_delta>,<score_delta>,<quality>
```

`AUDIT` 行的四个值依次为 `A["files"]`、`A["changes"]`、`A["failed"]`、
`A["quality"]`；`WORST` 行的六个值依次为 `A["worst"]` 的六项原值。所有
值直接取自 `A`，不重算、不重新排序：`int` 按十进制渲染，`str` 原样，
`float` 用 `format(v, ".6f")`（负零渲染为 `0.000000`）。

### `serialize_audit_report(path) -> bytes`

把一份审计 JSON 导出为带模式版本的报告字节串。

执行时**仅调用一次** `load_audit(path)` 得到 `A`，不调用任何其他加载或
汇总函数；因此 `path` 的校验契约、读取行为与异常完全沿用 `load_audit`：
非 `str` 抛 `TypeError`，空串抛 `ValueError`，文件缺失抛
`FileNotFoundError`，目录抛 `IsADirectoryError`，其余 `OSError` 原样传
播，解析、结构或规范字节非法抛 `ValueError`。输入文件不会被修改。

返回紧凑 UTF-8 JSON 字节，顶层键序为
`schema_version, source, summary, worst, quality`：

- `schema_version` 为非布尔整数 `1`；
- `source` 的键序为 `path, kind`，值依次为原 `path` 与固定字符串
  `"audit"`；
- `summary` 的键序为 `files, changes, failed, passed, pass_ratio`：前三
  项直接取 `A["files"]`、`A["changes"]`、`A["failed"]`，
  `passed = changes - failed`，
  `pass_ratio = round(float(passed / changes), 6)`；
- `worst` 的键序为 `file_index, index, degraded_delta, coverage_delta,
  score_delta, quality`，六值依次取 `A["worst"]` 的六项原值；
- `quality` 取 `A["quality"]`。

计数为 `int`，两个 delta 与 `pass_ratio` 为 `float`。JSON 字节格式、浮
点六位舍入、负零归一化及编码失败抛 `ValueError` 的规则沿用
`serialize_audit`；不重算最差项、不修改 `A`、不增加额外键。

### `load_audit_report(path) -> dict`

读取一份 `serialize_audit_report` 产出的审计报告 JSON。

`path` 校验、二进制（`"rb"`）读取与系统异常、BOM/尾换行拒绝、UTF-8/JSON
解码、`NaN`/`Infinity` 与重复键拒绝以及逐字节规范重序列化核对，全部沿用
`load_audit`：非 `str` 抛 `TypeError`，空串抛 `ValueError`，文件缺失抛
`FileNotFoundError`，目录抛 `IsADirectoryError`，其余 `OSError` 原样传
播；解析、结构或规范字节不符一律抛 `ValueError`。文件不会被修改。

解码值必须是 JSON 对象，顶层键序恰好为
`schema_version, source, summary, worst, quality`——重复、缺失或多余键
均被拒绝：

- `schema_version` 为非布尔整数 `1`；
- `source` 为对象，键序恰好为 `path, kind`：`path` 为非空 `str`，`kind`
  为固定字符串 `"audit"`；
- `summary` 键序恰好为 `files, changes, failed, passed, pass_ratio`：前四
  项为非布尔 `int`，满足 `files >= 2`、`changes >= files`、
  `0 <= failed <= changes`、`passed = changes - failed`；`pass_ratio` 为
  有限非布尔 `float`，等于 `round(float(passed / changes), 6)`，禁止负零；
- `worst` 为对象，键序恰好为
  `file_index, index, degraded_delta, coverage_delta, score_delta,
  quality`：前三项为非布尔 `int`，满足 `0 <= file_index < files`、
  `index >= 1`、`-2 <= degraded_delta <= 2`；`coverage_delta` 与
  `score_delta` 为有限非布尔 `float`，分别落在 `[-2, 2]` 与
  `[-200, 200]`，各自等于 `round(float(v), 6)` 且禁止负零；`quality` 为
  `"pass"`/`"fail"`——其类型、范围、六位舍入、负零与质量联动规则沿用
  `load_audit` 的 `worst`；
- 顶层 `quality` 仅为 `"pass"`/`"fail"`，当且仅当 `failed = 0` 时为
  `"pass"`，此时 `worst.quality` 也必须为 `"pass"`。

返回保持原键序的 dict（`source`、`summary`、`worst` 亦保持其存储键序），
各值原样返回，文件始终不被修改。

### `export_audit_report(audit_path, output) -> bytes`

把一份审计 JSON 序列化为审计报告字节串后原子写盘，并返回所写字节。

执行时**先且仅调用一次** `serialize_audit_report(audit_path)` 得到字节串
`B`，在此之前不做任何其他工作、之后也不再调用第二次；因此 `audit_path`
的校验契约、异常（原样向上传播）与文件不变性完全沿用
`serialize_audit_report`，且 `audit_path` 的错误先于 `output` 报出。审计
文件不被修改。

随后才校验 `output`：必须为非空 `str`——非 `str` 抛 `TypeError`
（`output must be a str`），空串抛 `ValueError`
（`output must not be empty`）。

`output` 不得与 `audit_path` 指向同一文件：双方都存在时用
`os.path.samefile` 识别软/硬链接，任一方不存在时比较
`os.path.normcase(os.path.realpath(os.path.abspath(path)))`；重合时抛
`ValueError`。

非重合时在 `output` 同目录创建临时文件，以二进制写入 `B`，`flush()`、
`os.fsync()` 后用 `os.replace` 原子替换 `output`。替换前发生失败会清除
临时文件且既有 `output` 逐字节不变；`OSError` 原样传播。返回值与写入文件
的字节为同一份 `bytes`，`audit_path` 指向的文件不被修改。

### `render_audit_report(path) -> str`

把一份审计报告 JSON 渲染为三行汇总文本。

执行时**仅调用一次** `load_audit_report(path)` 得到 `R`，不调用任何其他
加载或汇总函数；因此 `path` 的校验契约与异常完全沿用
`load_audit_report`：非 `str` 抛 `TypeError`，空串抛 `ValueError`，文件
缺失抛 `FileNotFoundError`，目录抛 `IsADirectoryError`，其余 `OSError`
原样传播，解析、结构或规范字节非法抛 `ValueError`。输入文件不会被修改。

返回以 `\n` 连接、无尾换行的三行：

```
REPORT=<schema_version>,<source.path>,<source.kind>,<quality>
SUMMARY=<files>,<changes>,<failed>,<passed>,<pass_ratio>
WORST=<file_index>,<index>,<degraded_delta>,<coverage_delta>,<score_delta>,<quality>
```

`REPORT` 行的四个值依次为 `R["schema_version"]`、`R["source"]["path"]`、
`R["source"]["kind"]`、`R["quality"]`；`SUMMARY` 行的五个值按
`R["summary"]` 的键序，`WORST` 行的六个值按 `R["worst"]` 的键序。所有值
直接取自 `R`，不重算、不重新排序：`int` 按十进制渲染，`str` 原样，
`float` 用 `format(v, ".6f")`（负零渲染为 `0.000000`）；`source.path`
用 `json.dumps(v, ensure_ascii=False, separators=(",", ":"))` 渲染。
