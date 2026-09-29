# 发布流程（GitHub 公开 + Zenodo DOI）

[English](RELEASE.md) | 中文

本文件只描述**由维护者手动执行**的两步发布。仓库内已把所有元数据准备好，
唯一待填的是 Zenodo 铸出 Concept DOI 后的 `CITATION.cff` 占位符
（见下方"粘贴位置"）。

版本号当前为 `0.1.0`，以下五处保持一致（发布前请再次核对）：
`geophylo/_version.py`、`pyproject.toml`、`CITATION.cff`、`.zenodo.json`
和 `CHANGELOG.md` 的版本标题（`tests/test_packaging.py` 的
`test_version_agrees_across_release_files` 正是钉这五处）。

---

## 步骤 1 — 公开仓库并创建 release

1. GitHub → 目标仓库 → **Settings → General → Danger Zone → Change repository
   visibility → Make public**。公开前确认工作树干净，即没有未跟踪的文件
   （`git status --short` 的输出应为空）。
2. 打标签并发布 release（本地命令，二选一；标签名是 `v` 前缀 + 版本串）：

   ```bash
   VERSION=0.1.0
   git tag -a "v${VERSION}" -m "geophylo ${VERSION}"
   git push origin main "v${VERSION}"
   gh release create "v${VERSION}" --latest --title "geophylo ${VERSION}" --generate-notes
   ```

   或在网页 **Releases → Draft a new release**：Tag 填 `v${VERSION}`（即 `v` + 版本
   串），Target `main`。

3. **`.zenodo.json` 必须位于该 tag 指向的提交里**（Zenodo 读的是 release 的
   快照，不是分支 HEAD）。上一步先提交、后打标签即可满足。

## 步骤 2 — 铸造 Zenodo DOI

1. 用同一个 GitHub 账号登录 <https://zenodo.org/account/settings/github/>，
   把 `ZengZichao/GeoPhylo` 的 **repository synchronization** 打开。
   若 release 已经存在，而该开关是事后才打开的，请回到 release 页面点击 Zenodo
   徽章（或在 `zenodo.org → Your uploads → New upload → Import` 里选中该
   release），补一次导入。
2. Zenodo 会用 `.zenodo.json` 预填草稿；其中 `version` 和 `publication_date`
   由 tag 元数据覆盖，属正常现象。**不要**在 `.zenodo.json` 里写 `conceptdoi`
   ——两个 DOI 都由 Zenodo 生成。
3. 人工核对草稿后点 **Publish**，记下两个号：
   - **Concept DOI** `10.5281/zenodo.XXXXXXXX`：跨版本不变，用于长期引用；
   - **Version DOI**：本次发布特有，用于精确复现。
4. 许可提示：本仓库产物里同时含有 **CC-BY-4.0** 的 ICS 快照数据，而 Zenodo
   单条记录只能填一个 `license`，因此记录里填 `MIT`。数据侧的归属说明由三处
   共同承担：`.zenodo.json` 的 `notes` 字段、仓库内的 `NOTICE` 和
   `LICENSES/CC-BY-4.0.txt`。发布时请保留 `notes`。

## 粘贴位置

| 目标 | 位置 | 填什么 |
| --- | --- | --- |
| `CITATION.cff` | `identifiers[0].value`（当前是 `10.5281/zenodo.REPLACE_AT_FIRST_RELEASE`） | Concept DOI |
| 可选 | `README.md` 顶部徽章、`docs/user-guide.*.md` 引用节 | Version DOI 徽章 `https://zenodo.org/badge/DOI/<version-doi>.svg` |

填写完成后，请一并删除 `CITATION.cff` 里那条 `REPLACE_AT_FIRST_RELEASE` 注释行。
随后在发布新的 release 之前，重新执行步骤 2。Zenodo 会派生新版本记录，Concept DOI
保持不变。

## 发布后复核

```bash
# 门禁套件：命令与 .github/workflows/ci.yml 顶部的权威定义逐字一致
# （必须带 --mpl；不排除 experimental，否则环形路径落在复核范围之外）。
pip install -e ".[test]"
MPLBACKEND=Agg pytest -m "not performance" -v --mpl \
    --mpl-baseline-path=tests/baseline_images

# 清洁室检查：必须在**隔离 venv** 里做，不能沿用上面 `pip install -e` 的解释器——
# 后者已把源码树放进 sys.path，check_wheel.py 的 `from geophylo import Timescale`
# 会导入源码而非发行物，"清洁安装"判定形同虚设（做法与 ci.yml 的 clean-room
# job 一致）。
python -m build
python -m venv clean-room
clean-room/bin/pip install --upgrade pip
clean-room/bin/pip install dist/*.whl
clean-room/bin/python tests/packaging/check_wheel.py dist

grep -R "geophylo/geophylo\|REPLACE_AT_FIRST_RELEASE" . --exclude-dir=.git \
    --exclude=RELEASE.md --exclude=CHANGELOG.md   # 除本文件与历史记录外应无输出
```
