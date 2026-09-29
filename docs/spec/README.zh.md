# 规范索引（Normative Specification Index）

[English](README.md) | 中文

本仓库的源码注释和 docstring 里出现的“规范 N.N”（以及紧随其后的裸节号，如
`（4.8）`、`（5.2 硬约束）`）都指向本页的同名条目；每条规范性主张都必须随包发布，
这样代码声称实现的契约可以直接被查阅与核验。每个节号有两个去处：写进它所约束代码
的 docstring（可直接执行、可直接测试），或者写进本页。**仓库之外不存在需要查阅的
开发文档**。

约定：

* “载体”列给出该条规范当前写在哪段代码或哪份文档里。主张以该处的文字为准，本页
  只做**索引 + 不可下沉到代码的部分**（跨模块不变量、取值理由、验收口径）。
* “可核验方式”列给出证明该条成立的测试或探针。新增规范条目必须同时给出可核验
  方式，否则该条目只是一句口号。
* 未被本页收录的节号就是失效引用，请按缺陷处理并修正。

## 1 定位与范围

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 1.3 | 本库只绘制地质时间轴，不绘制树；树由调用方绘制，坐标语义经 `CoordinateSpec` 或 `RadialSpec` 传入 | `geophylo/__init__.py`、`docs/user-guide.*.md` 第 1～2 节 | `examples/circular_tree.py`（树自绘 + `add_geo_ring`）；`tests/test_polar.py::TestCircularTreeRecipe` |
| 1.4 | 稳定性矩阵：稳定 API = `Timescale`、`Interval`、`Boundary`、`CoordinateSpec`、`spec_from_biophylo`、`add_geo_axis`、`GeoAxisResult`、`TimescaleBackend` 和 `GeophyloError`；实验性符号 = `add_geo_ring`、`RadialSpec`、`radial_spec_from_biophylo` 和 `spec_from_iplotx`（API 不冻结） | `geophylo/__init__.py` docstring；`README.md` 功能总览 | `tests/test_packaging.py`（顶层导出面）；`pyproject.toml` 的 `experimental` marker |
| 1.5 | 验收口径：12×8 英寸、`label_size=6`、`ranks=["Period","Epoch"]` 基准图上，隐藏的区间名标签 ≤ 20% | `docs/user-guide.*.md` 第 6 节 | `tests/test_add_geo_axis.py::TestLayoutInvariants::test_label_visibility_baseline` |

## 2 数据后端

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 2.2 | pyrolite 后端三条规则：严格 rank 过滤不回退、缺失元数据标 `unknown`（颜色用中性占位并告警，不伪造）、版本下界取 `MIN_PYROLITE_VERSION` | `geophylo/data/pyrolite_backend.py` 模块 docstring 与 `_true_rank`、`_row_age` 的 docstring | `tests/test_pyrolite_backend.py`（需 pyrolite，缺失即 skip）、`tests/test_timescale_query.py::TestPyroliteRankHeuristic`（判据适用面） |
| 2.3 | 后端协议 `TimescaleBackend` 的四条查询通道；`Interval`、`Boundary`、`BackendMetadata` 的字段语义（含 `uncertainty_ma=None` ≠ 误差为 0） | `geophylo/data/backend.py`、`geophylo/data/models.py` | `tests/test_models.py`、`tests/test_data_contract.py` |

## 3 输入约束

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 3.2 | 公共参数校验助手是类型与取值域的唯一入口：第三方原始异常不得冒泡为公共契约 | `geophylo/validation.py`、`geophylo/exceptions.py` 模块 docstring | `tests/test_exceptions.py`、`tests/test_add_geo_axis.py::TestInputValidation` |

## 4 公共 API 契约

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 4.1 | `Timescale` 是统一查询门面；`age_range`（合法域）与 `min_age`、`max_age`（绘制窗口）分离；窗口语义为“相交后裁剪” | `geophylo/timescale.py`、`geophylo/render/linear.py::_window_intervals` | `tests/test_timescale_query.py`、`tests/test_add_geo_axis.py::test_ediacaran_partial_overlap_drawn_clipped` |
| 4.2 | 年龄归属四条：① 结构节点不参与命中；② 边界值归属于以其为 `older_ma` 的较年轻区间（左闭右开）；③ `0.0` 归最年轻（present）区间；④ 多 rank 同时命中返回最具体者（Age>Epoch>Period>Era>Eon），吸附容差 1e-9 | `geophylo/data/_query.py`（`core_rank_pool`、`resolve_age`、`present_youngest`、`age_hit` 的 docstring） | `tests/test_timescale_query.py`、`tests/test_adapter_biopython.py::TestDegenerateTree`（跨后端一致性由 `_query` 单测固定） |
| 4.3 | 名称查询三通道 `name → aliases → label`，通道内精确匹配优先，无精确命中才回退子串；命中 0 个或 ≥2 个时，分别抛 `IntervalNotFoundError`、`AmbiguousIntervalError` | `geophylo/data/_query.py::search_by_name` | `tests/test_timescale_query.py::TestQueries` |
| 4.4 | `add_geo_axis()`、`add_geo_ring()` 的输入约束与拒绝行为；`update()` 与创建路径共用同一套取值域校验 | `geophylo/render/linear.py::add_geo_axis`、`geophylo/render/result.py::validate_render_params` | `tests/test_add_geo_axis.py::TestInputValidation`、`tests/test_lifecycle.py::TestUpdateValidation` |
| 4.5 | 生命周期：`update()` 全量校验后才提交（失败不改动状态）；`sync()` 的两层语义；`finalize()` 固化精确布局；`remove()` 只在宿主视图未遭用户改动时自动还原 | `geophylo/render/result.py` 各方法 docstring | `tests/test_lifecycle.py`、`tests/test_add_geo_axis.py` |
| 4.6 | 刻度契约：`format_age` 黄金样例（`0.0→"0.00"`、`1.0→"1"`、`66.0→"66"`、`538.8→"539"`）、`dedupe_ages` 容差 1e-9、`fill_ages_style` 的 20% 阈值、`cap_ticks` 的三级优先与“从最老端起”方向、像素间距 `2 × label_size` 过滤；`boundaries` 样式不受 `tick_max_count` 约束、`tick_style="ages"` 受之约束，丢弃数量记录在 `GeoAxisResult.ticks_dropped` | `geophylo/render/ticks.py`、`geophylo/render/linear.py::_draw_ticks`、`geophylo/render/result.py::GeoAxisResult.ticks_dropped` | `tests/test_ticks.py`、`tests/test_add_geo_axis.py::TestTicksRendered` |
| 4.7 | 异常体系：全部公共异常继承 `GeophyloError`；`AmbiguousIntervalError` 同时是 `IntervalNotFoundError` 的子类（只为让只捕获“查不到”的调用方代码继续工作），捕获顺序见用户手册异常表 | `geophylo/exceptions.py`、`docs/user-guide.*.md` 第 12 节 | `tests/test_exceptions.py` |
| 4.8 | 环形路径五条硬约束：单 rank；仅原生 `PolarAxes`；环段半径 = `spec.age_to_radius(age, radius_range=band_radius(band))`（**`band` 参与几何**）；`band` 越出当前 `rlim` 抛 `InvalidRadiusError`；从不调用 `set_rlim`、`set_rorigin` | `geophylo/render/polar.py` 模块 docstring 与 `add_geo_ring`、`_validate_band`、`rebuild` | `tests/test_polar.py::TestBandGeometryDrivesRingRadii`、`TestNoRadialViewModification` |
| 4.9 | 一致性契约：环与树共用同一个 `RadialSpec`；`age_to_radius` 是 `age_range → radius_range` 的严格单调递减仿射映射，值域限制仍是同一条映射（不另立第二套公式）；`radius_to_age` 在同一值域上精确可逆 | `geophylo/coordinate/radial.py` 模块 docstring 与 `age_to_radius`、`radius_to_age`、`band_radius` | `tests/test_radial_spec.py::TestRadiusMapping`、`tests/test_polar.py::TestBandGeometryDrivesRingRadii` |
| 4.10 | 适配器强制根基线为 `None` 或 `0`；非零根 branch length 显式拒绝并给出两条修复路径；退化树（单叶或全零分支长度）显式报出成因 | `geophylo/adapter/biopython.py::_scan_tree`、`_require_positive_span` | `tests/test_adapter_biopython.py::TestDegenerateTree`、`tests/test_polar.py::test_zero_root_offset_required` |
| 4.11 | 渲染参数取值域：`thickness_ratio ∈ (0, 0.5]`、`alpha ∈ [0,1]`、`label_size > 0`、`tick_max_count ≥ 1`、`skip` 必须是字符串序列 | `geophylo/validation.py`、`geophylo/render/result.py::validate_render_params` | `tests/test_lifecycle.py::TestUpdateValidation` |

## 5 渲染层

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 5.1 | 轨道用 inset Axes 承载（ADR-2）：bounds 为宿主 Axes 比例，时间维数值**复制**宿主 limits 但不 sharex；边框按 near、far 语义单独画 `Line2D` | `geophylo/render/linear.py::_make_track_axes`、`_align_track_to_host`、`_draw_borders` | `tests/test_add_geo_axis.py::TestSideEffects`、`TestTrackGeometry` |
| 5.2 | 厚度分配两条不变量（可行性预检在分配前、总量守恒）；标签降级顺序 ①缩写 ②旋转 ③隐藏，不跳步；**两个几何硬约束对候选旋转角求值**，且标签沿时间维夹进轨道矩形；图面缩写只接受单段短代码，复合 `ccgmShortCode` 回退全名 | `geophylo/render/linear.py::compute_track_layout`、`geophylo/render/labels.py::apply_label_degradation`、`is_figure_abbreviation` | `tests/test_add_geo_axis.py::TestLayoutInvariants`、`tests/test_labels.py`（`TestAbbreviationGate`、`TestDegradation::test_rotated_candidate_*`、`test_edge_label_*`） |
| 5.3 | 环形标签按 `theta_range` 中点确定性放置，不参与降级流程；`rotate_labels=True` 时角度 = `degrees(theta_center) + rotation` | `geophylo/render/polar.py::relayout`、`rebuild` | `tests/test_polar.py::TestRotateLabelsRadialAlignment` |
| 5.4 | 自动对比色：先做 alpha 合成，再按 sRGB 线性化和 WCAG 相对亮度判定黑色或白色，平局偏向黑色；示例统一顺序 `add_geo_axis → tight_layout → finalize → savefig` | `geophylo/render/labels.py::auto_label_color`、`examples/*.py` | `tests/test_labels.py::TestAutoLabelColor`、`tests/test_packaging.py`（示例执行） |
| 5.6 | 逐边界状态模型：`qualifier`（数值性质）与 `definition`（界线定义方式）正交；`unknown` 一律 `uncertainty_ma=None` | `geophylo/data/models.py`（`Boundary` docstring）、`docs/adr/ADR-5-*.md` | `tests/test_models.py`、`tests/test_data_contract.py` |
| 5.7 | 快照生成与哈希：`payload_sha256` 覆盖 `intervals` 数组（元数据不受保护，见 `PROVENANCE.md`）；加载即校验 | `geophylo/data/builtin.py`（`canonical_payload_bytes`、`load_snapshot`、`SnapshotBackend`）、`docs/data-policy.md` | `tests/test_data_contract.py`、`tests/test_snapshot_provenance.py` |

## 6 适配与配方

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 6.1 | 坐标对齐论证：Bio.Phylo 的 x 是到根的累积 branch length，因此适配器恒定产出 `mode="root_distance"`；`age_range` 取数据域而非 view limits；不检查超度量性和叶年龄是设计特性 | `geophylo/adapter/biopython.py` 模块与 `spec_from_biophylo` docstring | `tests/test_adapter_biopython.py`、`tests/test_coordinate_spec.py` |
| 6.2 | iplotx 适配器：读 `get_layout()` 的布局数据域，`age_conversion` 作用在根距离上；radial 布局显式拒绝 | `geophylo/adapter/iplotx.py` 模块 docstring | `tests/test_adapter_iplotx_contract.py`、`tests/test_adapter_iplotx.py`（缺 `ete4` 或 `iplotx` 时 skip） |
| 6.3 | 环形树配方（约 30 行）：角域按叶均分、内部节点取子节点角均值、半径一律查同一个 `RadialSpec` | `examples/circular_tree.py`、`docs/user-guide.*.md` 第 9.3 节 | `tests/test_polar.py::TestCircularTreeRecipe` |

## 7 数据与文档一致性

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 7.1 | 参数表与代码逐项一致（参数名、默认值、rank 权重、6 px 下限、`label_size × 2` 像素间距规则） | `docs/user-guide.*.md` 第 6 节 ↔ `geophylo/render/linear.py` | `tests/test_docs_values.py` |
| 7.2 | 容差取值：共享边界一致性与父子包含用 1e-9（`geophylo/data/builtin.py::_TOL`）；边界吸附与窗口贴边同值（`_query.SNAP_TOL`）。取值理由：上游年龄最多 4 位小数（如 Holocene 底 0.0117 Ma），1e-9 远小于任何有意义的地质时间差，又能吸收 JSON 往返的浮点噪声 | `geophylo/data/builtin.py`（`_TOL` 注释）、`geophylo/data/_query.py`（`SNAP_TOL`） | `tests/test_data_contract.py`、`tests/test_timescale_query.py` |
| 7.4 | 宿主视图状态零改动承诺：`add_geo_axis()` 不改 limits、scale、autoscale 和 `dataLim`；`remove()` 不反向改写用户在其间设置的视图 | `geophylo/render/result.py::remove`、`AxesState.matches`、`README.md`、`docs/user-guide.*.md` 第 7 节 | `tests/test_add_geo_axis.py::TestSideEffects`、`tests/test_lifecycle.py::TestRemoveDoesNotStompUserView` |
| 7.7 | 文档数值纪律：面向用户的文档里的 `<数值> Ma` 必须来自内置快照边界集合；示例脚本不得手写快照边界值 | `docs/user-guide.*.md`、`README.md`、`examples/*.py` | `tests/test_docs_values.py` |
| 7.8 | 能力声明测试与非阻塞约定：实验性后端的能力测试不阻塞发布门禁 | `geophylo/data/pyrolite_backend.py` 模块 docstring、`pyproject.toml` markers | `tests/test_pyrolite_backend.py` |
| 7.9 | 仓库文档结构约定：每份 ADR 都写出被否方案；`RELEASE.md` 是编号的两步手动流程；边界取值域在 `models.py` 的类型声明与加载器的校验集合同源 | `docs/adr/ADR-1…5`、`RELEASE.md`、`geophylo/data/models.py` ↔ `geophylo/data/builtin.py` | `tests/test_docs_values.py`（`test_every_adr_documents_its_rejected_alternatives`、`test_release_notes_describe_a_two_step_procedure`、`test_boundary_value_domains_match_between_models_and_loader` 与一条 planted 反例） |

## 8 出处与复现

| 节号 | 规范性主张（摘要） | 载体 | 可核验方式 |
| --- | --- | --- | --- |
| 8.2 | 后端能力矩阵（有无稳定 ID、误差、GSSP 状态和颜色）必须显式声明，“不知道”和“没有”可区分 | `geophylo/data/models.py::BackendMetadata`、两后端的 `metadata` | `tests/test_pyrolite_backend.py`、`tests/test_data_contract.py` |
| 8.4 | 快照出处（含推导快照 2024/12 的 `derived_from`、生成日志、逐字段 diff）随包发布，并与数据字节互相校验 | `geophylo/data/snapshots/PROVENANCE.md`、`docs/data-policy.md`、`tools/build_snapshot.py` | `tests/test_snapshot_provenance.py` |
