# 数据政策：来源、许可、快照更新和回退

[English](data-policy.md) | 中文

本文件说明 `geophylo` 内置 ICS 快照的数据来源、生成方式、许可合规和更新流程
（见[规范索引](spec/README.md)第 5.7 节、第 8.4 节）。

## 来源

- 内置快照直接从 ICS 官方版本化数据生成，**不从 `pyrolite` 二次复制**。
- 固定来源（两个快照共用同一份锁定输入，pinned input）：
  - 仓库：`i-c-stratigraphy/chart`
  - tag：`v2026-06.5`（官方 `2026-06` 图表版本发布）
  - commit：`44d1043ecf295cce1be03b3fc5fa95ca65fe770b`
  - 文件：`chart.ttl`
  - 上游文件 SHA-256：`0158959e8fdae2a8bdbb14ca3e424d2370362cd8dfc8af86e7be73c74368b355`
  - 仓库内副本：`tools/source/ics-chart-v2026-06.5.ttl`
- “锁定输入”不是一句文字声明，而是可机器复核的三重断言：`versions.json` 顶层
  `pinned_input.{file,sha256,bytes}` == 磁盘上随仓库归档的副本的 SHA-256 == 两份
  快照的 `source.source_sha256` == 构建时 `--source-sha256` 与实际读入字节的比对
  结果。四者不符时直接拒绝产出。
- 守卫代码在 `tools/build_snapshot.py::rebuild_index` 与
  `tests/test_snapshot_provenance.py`，后者包含篡改即失败的用例。
- 图表版本与快照文件的对应关系（每个图表版式只发布一个修订）：
  - `2026/06`（基线快照，`versions.json` 标注）→ `ics_chart-2026-06.json`
    （`snapshot_revision` 1）
  - `2024/12` → `ics_chart-2024-12.json`（`snapshot_revision` 1）

注意措辞：`2026/06` 是本项目的**基线快照**，不是“当前版本”。ICS 会持续发布新版
图表，任何快照都不是当前版本。

引用年份和图表版本是两件事，二者在本仓库里分别记录，不得混写：

- 引用年份：**2025**（Cohen, K. M., Harper, D. A. T., Gibbard, P. L. & Car, N.
  (2025, updated). *The ICS International Chronostratigraphic Chart this
  decade.*）两个快照的 `license.citation`、`NOTICE` 和 `CITATION.cff` 的数据集
  引用条目全部使用 2025。
- 图表版本：**2026/06**（上游 tag `v2026-06.5`）写在快照的 `chart_version`、
  `versions.json` 和 `CITATION.cff` 数据集引用的 `edition` 字段里。

## 确定性生成

`tools/build_snapshot.py` 按[规范索引](spec/README.md)第 5.6 节、第 5.7 节的契约
生成快照：

- 同一输入文件产出逐字节相同的 JSON。生成过程不读当前时间，即不导入 `datetime`
  和 `time`。`retrieved-at` 必须显式传入，且只写入生成日志，绝不写入快照本体。
- `hash.payload_sha256` 定义为对 `intervals` 数组做规范化 JSON 序列化（键排序、
  紧凑分隔符、UTF-8）后的 SHA-256。`versions.json` 是唯一版本索引。 `versions.json` 顶层的 `schema_version`（当前 2）是**索引格式**版本，与各快照文件顶层的 `schema_version`（当前 1，**记录结构**版本）不是同一个计数器，两者各自随自己的格式演进。
- `hash.provenance_sha256` 覆盖**除 `intervals` 和 `hash` 之外**的全部顶层元数据：
  `chart_version`、`snapshot_revision`、`source`、`license`、`derivation` 和
  `derived_from`。两把哈希各自承担一半披露：`payload_sha256` 保护科学数值，
  `provenance_sha256` 保护版本标签与来源块本身，因此只改写元数据也会留下哈希
  痕迹。`rebuild_index()` 复算并断言这两个哈希。
- 生成日志记录以下内容：完整命令行（`command`）、`--chart-version`、`--to`、
  `--tag`、`--commit`、`--source-sha256`、抓取时间、上游陈述计数（`parse_stats`）、
  边界回退清单、修复清单（`integrity_repairs`）、名称推导清单、别名去重清单、
  qualifier 分布和警告。
- 生成日志命名规范：`tools/build-logs/<快照名>.log.json`，即
  `ics_chart-2026-06.log.json`、`ics_chart-2024-12.log.json`。日志默认路径以
  **仓库根**为锚点（`default_log_path()`），在任意子目录执行同一条命令都落在同一
  位置。这些日志随仓库跟踪，属于出处工件，`.gitignore` 不得忽略它们，也不得引入
  任何会命中 `tools/build-logs/*.log.json` 的忽略规则。规范以本条为准。
- 两份快照的生成日志随仓库归档在 `tools/build-logs/`，由上文同一条命令产出。
  重跑 `tools/build_snapshot.py` 必须能逐字节重现快照本身
  （`tests/test_snapshot_provenance.py` 断言这一点），因此日志里的 `retrieved_at`、
  `out` 和 `command` 也是可核对的字面量。
- 版本之间的机器可读 diff 由 `tools/make_diff.py` 生成。写完快照后，
  `build_snapshot.py --diff-with <版本>` 也能一并产出该文件，前提是 `--diff-with`
  与本次 `--chart-version` 不同值——同值会被直接拒绝。基线与推导版的 diff 归档为
  `geophylo/data/snapshots/diff-2024-12_to_2026-06.json`。
  - 头部记录双方的图表版本、`snapshot_revision`、`payload_sha256` 和
    `source_sha256`，正文逐字段列出每条受影响记录的变化。
  - `boundary_age_changes` 一节把同一共享边界在多条目上的传播收敛为一处变化；
    共享边界上出现两种不同的误差迁移时显式失败，绝不静默保留首条。
  - 该文件不得手改：`tests/test_snapshot_provenance.py` 会在内存里重算，并与随包
    发布的字节比对。

### 2024/12 快照的推导

上游 changeNote（`skos:changeNote "2026-06: hasBeginning 246.7 -> 247.0"` 等）
记录了 2026/06 相对 2024/12 的三处边界更新：

1. Triassic base Anisian：246.7 → 247.0 Ma
2. base Olenekian：249.9 → 250.8 Ma
3. Permian base Wuchiapingian：259.51 ±0.21 → 259.857 ±0.084 Ma

`--to 2024/12` 按这些 changeNote 逐条回退，并恢复 Wuchiapingian 底界的误差
（0.084 → 0.21，上游 changeNote 只记录了年龄变化，未记录误差变化）。

`--to` 是回退集合的**唯一决定者**：过滤条件不得内嵌任何具体的图表版本字面量，
否则 `--to` 就不参与决策、任何取值都产出同一份“回退”数据。规则如下：

- 回退的是版本前缀**严格晚于** `--to` 的 changeNote；更早的修订保持生效。
- 每条 changeNote 必须带 `YYYY-MM:` 前缀，否则构建失败。上游换写法不会悄悄改变
  回退范围。
- `--to` 必须与 `--chart-version` 同值，且目标必须是 `DERIVED_SNAPSHOTS` 中登记过
  的版本；一条回退都没有时直接失败，禁止把基线数据贴上更早的标签。因此
  `--to 2026/06`、`--to 2030/01`、`--to 1999/01` 和 `--to nonsense` 一律拒绝构建。
- `derived_from.reverted_boundary_count` 由本次构建的**实际**回退条数写入，
  `rebuild_index()` 再拿它与生成日志的 `reverted_boundaries` 实长对账；对不上就
  拒绝重建索引。计数一律来自构建结果，不写成手写常量。

这份快照**不是**从上游 2024/12 归档版本抓取的，而是由同一条锁定输入回退推导而来，
因此它的 `source` 块与 2026/06 逐字节相同。该事实是机器可见的：

- `versions.json` 的 `2024/12` 条目带 `derived_from`，字段包括母版本、推导方法、
  生成器开关、锁定输入文件、回退边界条数和生成日志路径。`build_snapshot.py` 在
  构建时把它写入快照顶层，索引重建时负责搬运，因此字段不会丢失，内容也不允许
  手工改动。
- 人读版说明见 `geophylo/data/snapshots/PROVENANCE.md`。
- 未回退的变化：任何上游未写 `skos:changeNote` 的修订，在本快照里仍是 2026/06 的
  值。推导的完备性以上游自己的变更日志为限。
- “ICS 图表仓库不发布机器可读的 2024/12 Turtle 快照”这条前提属于**外部事实
  主张**：本仓库离线时无法核验它，因此 `PROVENANCE.md` 把这类主张显式标注出来，
  读者应把它们看作披露的假设，而不是既定事实。

### 上游数据瑕疵的确定性调和

生成器只修复上游数据里能用确定性规则证明的瑕疵，全部记入生成日志，并写进快照顶层
`derivation.integrity_repairs`（该字段在 `intervals` 之外，因此不改 payload 哈希，
却随包分发）：

- **少数派舍入值吸附**（`snap-minority-rounding-variant`）：判据是**结构等值类**，
  即同一条界线的三种结构关系：父底界 ≡ 最老子区间底界；父顶界 ≡ 最年亲子区间顶界；
  同父相邻子区间的公共界面。
  - 生效条件：类内两个写法相差不超过 0.05、少数派在全库只出现一次、主流写法至少
    出现两次（如 Aquitanian 底界 23.03 vs Miocene 底界及其四条同界记录的 23.04）。
  - 判据只看结构等值类，不做全局计数：全局计数与年代地层学无关，会把 Quaternary
    的 0.0117、0.0082、0.0042 和 0.0 当成“少数派”。这些值安全，是因为它们在各自
    结构类内部本就一致。判据不足时构建失败，构建器不做猜测。吸附之后
    `check_parent_containment()` 复验父子时间包含。
- **同 rank 重叠调和**（`same-rank-overlap-children-union`）：重叠时，若较老区间的
  子区间并集终点等于较年新区间的底界，生成器采信子区间端点（2026/06 上游 Ludlow
  端点 419.62 与其子 stage 并集终点 422.7 矛盾）。其余情形显式失败，交由人工裁决，
  不允许静默改数。并集计算用 `is not None` 判定，`0.0` 是合法端点值。
  - 搬动年龄时**同时清空**该端点上属于旧年龄的 `marginOfError` 和
    `skos:note "uncertain"`，因为它们是对旧值的陈述。跟着年龄走会在 422.7 上制造
    一条上游从未有过的“1.6 vs 1.36”误差冲突。
  - 清空的前提是目标年龄处另有独立误差凭据（422.7 的 ±1.6 由 Ludfordian 顶界与
    Pridoli 底界两处写出），否则构建失败。
- 生成器对无法解析的端点字面量、白名单外的端点谓词、缺 `hasBeginning` 或
  `hasEnd`、缺 `gts:rank` 的 `skos:Concept` 主体一律显式失败，绝不静默产出“仍能
  通过全部校验”的残缺快照。`derivation.parse_stats` 自述上游陈述计数，
  `tests/test_data_contract.py` 用一套独立解析器复核它（概念主体 178 个、端点值
  356 个、误差 206 条、`~` 标记 36 条）。

### 上游元数据的确定性推导

- `status`：有 `ratifiedGSSP/GSSA` 标记 → `ratified`；占位命名（Cambrian
  Stage/Series）→ `informal`；其余 → `unknown`（诚实缺失，不伪造）。
- 边界 `definition`：年龄 0 → `present`；该边界作为底界且任一同底界记录有
  ratified GSSP → `gssp`；GSSA → `gssa`；否则 `numeric_estimate`。
- 边界 `qualifier`（`tools/build_snapshot.py::boundary_qualifier`）有**三个**输入：
  `definition`、上游 `schema:marginOfError`（`±`）和 `skos:note "uncertain"`（图表
  上的 `~`）。规则按顺序：
  1. `definition == present` → `present`；
  2. 上游写了 `~` → `approximate`。**该条先于** GSSP/GSSA 判定：一条 GSSP 界线的
     数值本身可以是上游明示的近似值，把它记成 `defined`（“exactly defined”）就是
     用 definition 轴吞掉 qualifier 轴，违反 ADR-5 的正交性声明；
  3. GSSP/GSSA 且有公布 `±` → `constrained`；GSSP/GSSA 且无 `±` → `defined`；
  4. 非 GSSP/GSSA 且有 `±` → `constrained`；
  5. 其余 → `unknown`。
- `~` 和 `±` 可以共存：此时 `qualifier == "approximate"`，`uncertainty_ma` 照旧
  保留，两者不互相抹除（锁定输入里目前 36 处 `~` 均未同时给 `±`）。
- 两份出厂快照的 qualifier 分布均为
  `approximate 36 / constrained 208 / defined 97 / unknown 12 / present 5`
  （合计 358 个端点），与 TTL 里 36 条 `skos:note "uncertain"` 一一对应。
- 部分细分单元上游无 `@en prefLabel`，例如 Lower、Middle、Upper 系列名和 Tarantian、
  Cambrian 占位 Stage。显示名从 IRI 局部名确定性推导（`LowerJurassic` →
  `Lower Jurassic`），推导清单记入日志和 `derivation.derived_labels`（26 条）。这些
  字符串**同时决定 `id`**，属于对外稳定契约面：`ics:period:lower-jurassic` 这类 ID
  是本项目的推导值，不是上游给出的标识符；改推导规则会改 ID，因此是一次数据变更。
- 官方短代码（notation）作为 `aliases`；ICS 以大小写区分 epoch 级（`T3`）与 age 级
  （`t3`）代码。大小写折叠冲突时按 rank 优先级消解（Super-Eon < Eon < Era < Period
  < Sub-Period < Epoch < Age），同 rank 内按 id 字典序，落选者逐条记入
  `derivation.dropped_aliases`（35 条）和生成日志。**这是一处有意的数据损失**：
  `ics:age:anisian` 等 35 条记录的 `aliases` 因此为空，而 `find_by_name("T3")` 只
  命中世级记录。哪一级应当持有共享代码，需按 ICS 图表确认；确认之前不改动优先级，
  但丢失清单必须随包可见。
- `Pridoli` 同时声明 Age 与 Epoch（官方如此，图表在两个行位显示），快照为每个声明
  rank 各生成一条记录（`ics:age:pridoli` 与 `ics:epoch:pridoli`）。
- 端点级 `source_iri` 恒为 `null`：ICS 图表把端点写成空节点（blank node），没有可
  引用的稳定 IRI，该字段留给能给出端点 IRI 的外部后端。区间级 `source_iri`
  （`http://resource.geosciml.org/classifier/ics/ischart/<Concept>`）才是上游概念的
  可寻址标识。

## 快照更新流程

1. 更新 `tools/source/` 下的锁定输入，记录新的 tag、commit 和 SHA-256。
2. 生成新快照与机器可读 diff。diff 覆盖边界、误差、`~` 标记（`qualifier`）、名称、
   rank、颜色、状态和新增删除的区间。`make_diff.py` 的 `_BOUNDARY_SUBKEYS` 含
   `qualifier`，因此 `~` 的得与失都会进 diff，近似标记语义不会在版本之间静默丢失。
3. 运行完整性、TTL 真值和视觉回归测试；更新哨兵断言（记录数、各 rank 数量、
   qualifier 分布），并在 CHANGELOG 中说明。
4. 发布。**已发布快照的 `intervals` 只增不改**：新的图表版式 = 新文件 + 新
   `versions.json` 条目；同一版式下修正提取缺陷 = 抬升该文件的 `snapshot_revision`，
   并在 CHANGELOG 和 PROVENANCE 中说明原因。旧版快照必须保留，并通过
   `Timescale(version=...)` 继续可选用。科学数据变化至少触发 minor release；修正
   错误转录必须在 CHANGELOG 中单独列出。
5. `generator.version` 标记的是“用什么语义提取”，不是“哪一版包”，因此包版本抬升
   本身不改这个标签；只有提取语义（解析、调和、模式 schema）变化时才抬升它。

## 许可合规

- ICS 官方图表数据以 **CC-BY-4.0** 发布，版权和归属 International Commission on
  Stratigraphy。快照的 `license` 元数据、`LICENSES/CC-BY-4.0.txt` 和 `NOTICE` 记录
  归属与引用要求；sdist 和 wheel 均包含这些文件。
- 本库代码以 MIT 发布；代码许可不覆盖第三方数据文件。
- `ete4`（GPL-3.0-or-later）不是本库的**必需**依赖：只有当用户显式安装 `geophylo[iplotx]`
  这一 optional extra 时才会被拉入（iplotx 运行时 import 它却不自行声明，故由本库补进该
  extra）。核心安装与 MIT 代码本身不含 GPL 组件。
- 本库仅在 `geophylo[pyrolite]` 安装时导入 `pyrolite`，把它作为运行时可选后端；
  `pyrolite` 的数据不进入本库产物。
