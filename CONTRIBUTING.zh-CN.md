# 参与贡献

[English](CONTRIBUTING.md) | 中文

## 开发环境

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 质量门禁（阻塞发布的检查）

- `pytest -m "not performance" -v --mpl --mpl-baseline-path=tests/baseline_images`：
  阻塞门禁命令（权威定义见 `.github/workflows/ci.yml` 顶部注释）。单元、数据契约、
  集成、生命周期、视觉基准和打包测试必须全部通过；实验性符号的测试也在门禁内。
- `pytest -m "not experimental and not performance"`：按稳定性切片，只跑稳定 API，
  用于排除与实验性符号无关的干扰。
- `pytest -m performance`：本库增量耗时不随叶节点数显著增长。单独成 job 是因为
  它在 100/1,000/10,000 叶三档上计时（10,000 叶档只测本库增量、不重绘宿主树），
  且计时断言对共享 runner 的
  噪声敏感，不适合挡发布门；口径与信噪双判据见 `tests/test_performance.py` 的
  模块 docstring。
- `pytest tests/test_architecture.py`：包 import 图**无环**、且每条边都指向更低层，
  兄弟层（data/coordinate、render/adapter）互不依赖。这条守的是"按层推理改动影响面"
  这一整个架构的前提，`ruff` 的 `I` 规则只管导入排序、不管方向，所以必须单独断言。
  新增模块时要同步补 `tests/test_architecture.py` 的 `MODULE_LAYER` 层表，否则该测试
  会以"没有层归属"失败。
- `ruff check geophylo tests tools examples`、`ruff format --check geophylo tests tools examples`、
  `mypy`：零告警。范围与 `.github/workflows/ci.yml` 的 Lint/Type check 步骤逐字一致，
  提交前先在同样范围本地执行一次不带 --check 的 ruff format。
- 示例在 CI 中实际执行，而不是只做语法检查。

## 契约三角

公共 API 契约（`docs/spec/README.md` 第 4 节）、测试用例（第 7 节）和实现细节
（第 5 节）构成三角引用。修改其中任意一处，都必须同步核对另外两处。

## 快照与数据

- 已发布快照**只增不改**，更新流程见 `docs/data-policy.zh.md`。
- 快照更新必须同步更新哨兵断言，并在 CHANGELOG 中单独列出数据变化。
- 面向用户的文档（README、docs/、examples/）里的边界数值必须来自快照，并由文档
  数值测试校验，不得手写。

## 视觉基准图

- `tests/baseline_images/` 由当前依赖栈生成（`python3 tests/update_baselines.py`），
  是所有阻塞门禁比较的基准。
- `tests/baseline_images_min/` 存放**最低依赖组合**（最老 Python、
  `matplotlib==3.10.*`、`numpy==1.25.*`）渲染的同两张图；core-min 任务跑门禁前
  会把它们拷贝到 `tests/baseline_images/`——3.10 的 Agg 输出与当前版本在抗锯齿
  层面有差异，而容差为零。再生成方法相同，在最低依赖环境里执行：
  `MPLBACKEND=Agg pytest tests/test_visual.py --mpl --mpl-baseline-path=tests/baseline_images --mpl-results-path=<目录>`，
  然后把 `<目录>/*/result.png` 拷入 `tests/baseline_images_min/`
  （matplotlib 3.10 下 pytest-mpl 的 `--mpl-generate-path` 产物与其比较管线不一致）。

## 提交

- 使用约定式提交（conventional commits）：`feat:`、`fix:`、`data:`、`docs:` 和
  `test:`。
