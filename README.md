## 用途

本项目是「海洋探测建模与海底地形平台」的代码仓库，用于逐步实现该方向的建模与数据处理能力。

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

## 现有公开接口

- 命令行程序 `ocean-sonar-modeling`
- Python 包 `ocean_sonar`，其 `__version__` 为当前版本号
- `ocean_sonar.crosspoint` 模块中的 `pair`、`gate` 与 `pair_gate` 函数

### `pair(first, second, tolerance=1.0)`

将两条测线上位置重合的点配对。

- `first` 与 `second` 均为非空 list/tuple；每个点为三元 list/tuple `(x, y, d)`，字段须为有限的非 bool int/float，且 `d >= 0`。`tolerance` 须为有限的非 bool int/float 且 `> 0`。
- 校验顺序（首个错误即抛出）：`first` 容器 → 其非空 → `second` 容器 → 其非空 → 逐点校验（先 `first` 后 `second`，各自按下标顺序：点容器、长度、字段类型、有限性、`d >= 0`）→ `tolerance`（类型、有限性、正值）。类型不匹配抛 `TypeError`，其余违规抛 `ValueError`。点错误消息带前缀 `"first[i]: "` 或 `"second[j]: "`。
- 匹配规则：按 `first` 输入顺序处理，每个点匹配尚未使用的 `second` 点中未舍入二维欧氏距离最小且不超过 `tolerance` 者；距离相等时取 `second` 中输入顺序最早者。无可用匹配的 `first` 点被跳过，每个 `second` 点最多使用一次；若最终没有任何配对，抛 `ValueError`。
- 返回 tuple，按 `first` 输入顺序，元素为四元 tuple `(x, y, d1, d2)`，各项均为 float；`x`/`y`/`d1` 来自 `first` 点，`d2` 来自匹配到的 `second` 点。数值舍入到 6 位小数，负零归一化为 `0.0`。不修改输入。

### `gate(crossings, tolerances, min_mean_ratio=1.0, max_rmse_limit=1.0)`

对交叉点评估结果按汇总阈值把关。

- 先恰好调用一次 `dashboard_report(crossings, tolerances)`，其全部校验、首个错误顺序、异常（原样传播）与索引前缀在此同样适用；随后依次校验 `min_mean_ratio`、`max_rmse_limit`：均须为有限的非 bool int/float，`min_mean_ratio` 须落在 `[0, 1]`，`max_rmse_limit` 须 `>= 0`。类型不匹配抛 `TypeError`，非有限或越界抛 `ValueError`。
- 返回 dict，键序为 `report, checks, quality`。`report` 为 `dashboard_report` 返回的原 dict。`checks` 为 dict，键序为 `mean_ratio, max_rmse, within_ok, rmse_ok`：前两个为汇总中的 `mean_ratio`、`max_rmse` 浮点值（已按 6 位小数舍入、负零归一化为 `0.0`），后两个为布尔值 `mean_ratio >= min_mean_ratio` 与 `max_rmse <= max_rmse_limit`。`quality` 仅当 `report` 的 `quality` 为 `"pass"` 且两项检查均为真时为 `"pass"`，否则为 `"fail"`。不修改输入。

### `pair_gate(first, second, tolerances, match_tolerance=1.0, min_mean_ratio=1.0, max_rmse_limit=1.0)`

先配对再把关的组合接口。

- 先恰好调用一次 `pair(first, second, match_tolerance)` 得到配对 `P`，再恰好调用一次 `gate(P, tolerances, min_mean_ratio, max_rmse_limit)`；两者的校验、首个错误顺序、异常（原样传播）与索引前缀在此同样适用。不修改输入。
- 返回 dict，键序为 `pairs, report, quality`：`pairs` 为 `pair` 返回的原 tuple，`report` 为 `gate` 返回的原 dict，`quality` 为 `gate` 结果中的 `quality`。
