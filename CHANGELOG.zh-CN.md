# 变更日志

[English](CHANGELOG.md) | 中文

本文件记录本项目的全部重要变更。数据变更与代码变更分开列出（科学数据变化触发
的发布至少是次版本号提升；即使只是订正级补丁，转录修正也会列出）。

## [0.2.1] - 2026-10-27

诊断信息与文档修正版。公共 API、默认渲染行为、随包数据与三处数字产物均与 0.2.0
一致（图 3 重跑后 PNG/PDF 的 SHA-256 与交付件逐字节相同）。

### 新增
- 公共异常新增稳定机器码 `code`：类级声明 `data.validation`、`rank.invalid`、
  `interval.not_found`、`interval.ambiguous`、`range.invalid`、`radius.invalid`、
  `axes.type`、`coordinate.spec`，需要更细判别时可在调用点用 `code=` 按实例收窄。
  调用方与测试应据此分支，不再依赖消息文案或 `GEOPHYLO_LANG`。手册第 12 节
  新增“稳定机器码”一段，`tests/test_exceptions.py` 增加码形态、唯一性与
  实例收窄的契约用例。

### 修复
- 用户手册 FAQ 编号重复：新增的三条（多级地质年代环、ETE4/toytree、iplotx 径向）
  与原 Q11–Q14 撞号，现统一为 Q1–Q17；中文手册补齐同样三条，两份手册条目数一致。
- 手册中“径向适配器排在 v0.2”的过期承诺改为“更晚的 0.x 版本”。
- README 增“稳定性与路线图”一节，明确 0.2 不包含实验性符号的稳定化范围。

## [0.2.0] - 2026-10-26

### 新增
- `add_geo_axis(tick_format=...)`：`"default"` 保持原有取整规则，`"exact"` 按快照
  存储精度打印（`251.902` 不再印成 `252`），也可传入 `age -> str` 可调用对象。
- `add_geo_axis(track_register=...)`：`"uniform"` 使一条轨道在任一处被迫缩写时
  整轨改用官方代号，消除“代号 + 全名”混排。
- `add_geo_axis(fallback_truncation=...)`：可选的名称前缀回退（先取 n 个字符，
  必要时递减到 2 个），排在旋转之后、隐藏之前，让没有官方别名的拥挤区间不再只能
  隐藏。三者默认关闭，既有调用行为不变。
- `add_geo_axis(min_label_gap=...)`：同轨相邻标签沿时间维的最小净距（默认 0，只判
  相交）；净距在放置阶段执行，放不开的标签沿降级阶梯退让，而不是先画上再丢弃。
- `GeoAxisResult` 新增 `labels_shortened_n` / `labels_rotated_n`（**可见**标签计数），
  图注可直接引用；`labels_shortened` / `labels_rotated` 仍是“是否发生过”的布尔位。
- 新增 `docs/adr/ADR-6-render-overrides-opt-in.md`（中英），记录四个显式启用覆写的取舍
  与被否方案；ADR 份数守卫与各处编号引用同步更新。
- 下游作图脚本不再需要携带补丁：`relabel_boundaries`（刻度精度覆写）、
  `uniform_track_register`（整轨统一）、`prefix_fallback`（前缀回退）三处已删除，
  改用 `tick_format="exact"` / `track_register="uniform"` / `fallback_truncation=3`。
  等价重跑的产物逐字节一致。
- 新增 `examples/figures/fig2.py`、`fig3.py`、`fig4.py`、`figb3.py`：纯 ASCII 入口，供无法
  键入中文路径的环境复现论文数据图（输出仍按归档脚本的 stem 命名，重跑字节一致）。

### 变更
- 异常与警告消息默认改为英文，`GEOPHYLO_LANG=zh` 切回中文（`geophylo._i18n.msg`，
  双语在每个调用点并排书写，非机器翻译）。共迁移 203 处 `raise`/`warnings.warn`，
  覆盖 `validation`、`coordinate`、`render`、`adapter`、`data` 全部调用点。
- README/README.zh-CN：PyPI 可用性表述更正（`geophylo 0.1.1` 已于 2026-10-18 发布），
  徽章改为指向索引页版本。
- 归档元数据：`CITATION.cff` 与 `.zenodo.json` 的 `creators` 补第二位作者。

## [0.1.1] - 2026-10-02

维护性发布；公共 API 与随包数据无变化。

### 变更
- 维护自动化：Dependabot（暂缓 GitHub Actions 的 major 升级）、pre-commit
  钩子，以及社区健康文件（SECURITY、行为准则、issue/PR 模板、FUNDING）。

### 修复
- CI：min-deps 可视化门禁、sdist 安装检查与 CodeQL 质量告警；iplotx 契约
  测试统一为单一 `geophylo` 导入形式。
- 发布工作流现在在 tag 推送时构建 sdist + wheel 并挂到 GitHub Release。

## [0.1.0] - 2026-09-30

首次发布。

### 新增 — 稳定公共 API
- `Timescale`、`Interval`、`Boundary`：跨五个核心地质年代等级可复现地访问
  随包 ICS 快照，逐边界保留限定符/误差/定义状态。
- `CoordinateSpec`（`absolute_age` 与 `root_distance` 两种模式）；纯映射
  `age_to_data()`；只经 `from_data_limits()` 显式确认的推断式范围获取。
- `add_geo_axis()` + `GeoAxisResult`：内嵌 Axes 式线性地质时间轴，支持多等级
  轨道、数值刻度契约、标签自动降级、自动对比色、宿主 Axes 状态保持，以及
  带键的幂等注册表（`update/sync/finalize/remove/restore`）。
- `spec_from_biophylo()`：Bio.Phylo 适配器，校验分支长度并始终产生
  `root_distance` 语义。
- `TimescaleBackend` 协议；随包快照后端在加载时执行 schema、层级、重叠、
  共享边界与哈希校验。
- 以 `GeophyloError` 为根的异常体系。

### 新增 — 实验性
- `pyrolite_backend`（只读，版本锁定 `pyrolite>=0.3.7`；从
  `geophylo.data.pyrolite_backend` 导入）。
- 实验性符号（API 不冻结）：`RadialSpec`、`radial_spec_from_biophylo()`、
  `add_geo_ring()`（单等级、原生极坐标 Axes）、`spec_from_iplotx()`。

### 数据
- 随包基线快照 `2026/06`（ICS 图表 v2026-06.5，来源 commit 已钉定）与推导快照
  `2024/12`（经上游 changeNotes 回推，含已记录的吴家坪阶（Wuchiapingian）误差
  恢复）；见 docs/data-policy.zh.md。
