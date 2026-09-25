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

## Python 接口

包 `ocean_sonar` 的 `__version__` 为当前版本号。

交点相关接口位于 `ocean_sonar.crosspoint`，该模块导出：
`evaluate`、`report`、`pair`、`audit`、`profile`、`aggregate`、
`dashboard`、`dashboard_summary`、`dashboard_report`、`gate`、
`gate_report`、`pair_gate`、`pair_gate_report`。

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
