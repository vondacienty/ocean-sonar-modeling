## 用途

本项目是「海洋探测建模与海底地形平台」的代码仓库，用于逐步实现该方向的建模与数据处理能力。

当前处于基线状态：只有项目骨架，尚未实现任何业务算法。

## 环境与安装

- Python 3.11 及以上

```bash
python -m pip install -e .
```

## 测试

```bash
python -m pytest
```

基线尚无测试用例，收集到 0 个用例属预期结果。

## 命令行入口

安装后提供 `ocean-sonar-modeling` 命令：

```bash
ocean-sonar-modeling version    # 打印版本号
ocean-sonar-modeling --help     # 打印用法
```

## 现有公开接口

- 命令行程序 `ocean-sonar-modeling`
- Python 包 `ocean_sonar`，其 `__version__` 为当前版本号

## 限制

- 除版本查询外没有其他功能。
- 输入输出格式、数据来源与算法均尚未定义。
