"""Bilingual documentation parity guards (English authoritative <-> Chinese).

The rules below encode the defect classes that a manual zh/en audit kept
finding: code corrupted by translation, a section present in one language only,
a renamed heading whose table-of-contents anchor was forgotten, a shell
placeholder or formal-boundary term translated into the wrong Chinese word, and
a pair that lost its cross-language link.

Each check is a pure function over the two texts so it can be exercised against
synthetic defects (see the self-check tests at the bottom) without mutating a
document.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

PAIRS: list[tuple[str, str]] = [
    ("README.md", "README.zh-CN.md"),
    ("CHANGELOG.md", "CHANGELOG.zh-CN.md"),
    ("CONTRIBUTING.md", "CONTRIBUTING.zh-CN.md"),
    ("RELEASE.md", "RELEASE.zh-CN.md"),
    ("docs/user-guide.en.md", "docs/user-guide.zh.md"),
    ("docs/data-policy.md", "docs/data-policy.zh.md"),
    ("docs/spec/README.md", "docs/spec/README.zh.md"),
    ("docs/adr/README.md", "docs/adr/README.zh.md"),
    *(
        (
            f"docs/adr/ADR-{n}-{slug}.md",
            f"docs/adr/ADR-{n}-{slug}.zh.md",
        )
        for n, slug in (
            (1, "bundled-snapshots-over-pyrolite"),
            (2, "inset-axes-for-tracks"),
            (3, "result-object-not-axes"),
            (4, "adapters-build-contracts"),
            (5, "per-boundary-state-model"),
            (6, "render-overrides-opt-in"),
        )
    ),
]

EN_BY_ZH = {zh: en for en, zh in PAIRS}

IDS = [zh for _, zh in PAIRS]

_CJK = re.compile(r"[\u4e00-\u9fff]")
_FENCE = re.compile(r"^\s*```")
_PLACEHOLDER = re.compile(r"<[A-Za-z\u4e00-\u9fff][^<>\n]{0,60}>")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")

# `<数值> Ma` in the Chinese spec index translates a prose placeholder pattern
# that no reader ever types; the English side writes `<number> Ma`. Placeholders
# inside shell blocks have no such exemption (see _bad_placeholders).
PLACEHOLDER_ALLOWLIST = {"<数值>"}

# A formally defined chronostratigraphic boundary (a GSSP/GSSA-defined stage
# base) is 界线; the data-model endpoint, field and value is 边界. The library's
# own Chinese comments state the split (geophylo/data/models.py, the docstring
# of tools/build_snapshot.py). These surface forms invert it.
BAD_BOUNDARY_TERMS = (
    "GSSP 定义的边界",
    "GSSP定义的边界",
    "GSSP 边界",
    "GSSA 边界",
    "GSSP/GSSA 定义的边界",
)


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _strip_trailing_comment(line: str) -> str:
    quote: str | None = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in {'"', "'"}:
            quote = ch
        elif ch == "#" and i and line[i - 1] in " \t":
            return line[:i].rstrip()
    return line


def _fence_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] | None = None
    for raw in text.splitlines():
        if _FENCE.match(raw):
            if current is None:
                current = []
            else:
                blocks.append(current)
                current = None
            continue
        if current is not None:
            current.append(raw)
    return blocks


def _code_lines(text: str) -> list[list[str]]:
    """Fenced code with comments removed, block by block.

    Comment-only lines are dropped on both sides because translating them is
    expected; what must not move is the code itself.
    """
    out: list[list[str]] = []
    for block in _fence_blocks(text):
        kept: list[str] = []
        for raw in block:
            stripped = raw.strip()
            if not stripped:
                continue
            if stripped.startswith("#!"):
                kept.append(raw.rstrip())
                continue
            if stripped.startswith(("#", "//", "..")):
                continue
            code = _strip_trailing_comment(raw)
            if code.strip():
                kept.append(code.rstrip())
        out.append(kept)
    return out


def _diff_code_blocks(en_text: str, zh_text: str) -> list[str]:
    en_blocks, zh_blocks = _code_lines(en_text), _code_lines(zh_text)
    if len(en_blocks) != len(zh_blocks):
        return [f"fence count {len(en_blocks)} != {len(zh_blocks)}"]
    problems: list[str] = []
    for i, (en, zh) in enumerate(zip(en_blocks, zh_blocks, strict=True)):
        if en != zh:
            for line in en:
                if line not in zh:
                    problems.append(f"block #{i} English-only code: {line.strip()}")
            for line in zh:
                if line not in en:
                    problems.append(f"block #{i} Chinese-only code: {line.strip()}")
    return problems


def _headings(text: str) -> list[tuple[int, str]]:
    inside_fence = False
    found: list[tuple[int, str]] = []
    for raw in text.splitlines():
        if _FENCE.match(raw):
            inside_fence = not inside_fence
            continue
        if inside_fence:
            continue
        m = _HEADING.match(raw)
        if m:
            found.append((len(m.group(1)), m.group(2).strip()))
    return found


def _diff_headings(en_text: str, zh_text: str) -> list[str]:
    en, zh = _headings(en_text), _headings(zh_text)
    if len(en) != len(zh):
        return [f"heading count {len(en)} != {len(zh)}"]
    en_levels = [level for level, _ in en]
    zh_levels = [level for level, _ in zh]
    if en_levels != zh_levels:
        return [f"heading level sequence differs: {en_levels} vs {zh_levels}"]
    return []


def _slug(heading: str) -> str:
    """The in-page anchor convention both languages of this repository use.

    Validated against every existing anchor in all 14 documents; it is a
    self-consistency rule, not a claim about any particular renderer.
    """
    text = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", heading.lower())
    return text.strip().replace(" ", "-")


def _dead_anchors(text: str) -> list[str]:
    targets = {_slug(title) for _, title in _headings(text)}
    dead: list[str] = []
    for href in _LINK.findall(text):
        if href.startswith("#") and href[1:].lower() not in targets:
            dead.append(href)
    return dead


def _bad_placeholders(zh_text: str) -> list[str]:
    return [
        span
        for span in _PLACEHOLDER.findall(zh_text)
        if _CJK.search(span) and span not in PLACEHOLDER_ALLOWLIST
    ]


def _bad_boundary_terms(zh_text: str) -> list[str]:
    flat = re.sub(r"\s+", " ", zh_text)
    return [term for term in BAD_BOUNDARY_TERMS if term in flat]


def _missing_counterpart_link(text: str, counterpart: str) -> list[str]:
    name = counterpart.split("/")[-1]
    return [] if re.search(rf"\]\([^)]*{re.escape(name)}", text) else [name]


def _unresolved_links(rel: str, text: str) -> list[str]:
    base = (ROOT / rel).parent
    bad: list[str] = []
    for href in _LINK.findall(text):
        if href.startswith(("#", "http://", "https://", "mailto:")):
            continue
        target = href.split("#")[0]
        if not target:
            continue
        if not (base / target).exists():
            bad.append(f"{rel}: {href}")
    return bad


@pytest.fixture(scope="module")
def pair_texts() -> dict[str, tuple[str, str]]:
    return {zh: (read(en), read(zh)) for en, zh in PAIRS}


class TestFencedCodeSurvivesTranslation:
    @pytest.mark.parametrize("zh", IDS)
    def test_code_blocks_match_english(self, zh: str, pair_texts) -> None:
        en_text, zh_text = pair_texts[zh]
        assert _diff_code_blocks(en_text, zh_text) == []


class TestStructureParity:
    @pytest.mark.parametrize("zh", IDS)
    def test_heading_structure_matches(self, zh: str, pair_texts) -> None:
        en_text, zh_text = pair_texts[zh]
        assert _diff_headings(en_text, zh_text) == []

    @pytest.mark.parametrize("zh", IDS)
    def test_in_page_anchors_resolve(self, zh: str, pair_texts) -> None:
        en_text, zh_text = pair_texts[zh]
        assert _dead_anchors(en_text) == []
        assert _dead_anchors(zh_text) == []


class TestPlaceholdersAndTerms:
    @pytest.mark.parametrize("zh", IDS)
    def test_no_shell_placeholder_translated(self, zh: str, pair_texts) -> None:
        _, zh_text = pair_texts[zh]
        assert _bad_placeholders(zh_text) == []

    @pytest.mark.parametrize("zh", IDS)
    def test_formal_boundaries_stay_界线(self, zh: str, pair_texts) -> None:
        _, zh_text = pair_texts[zh]
        assert _bad_boundary_terms(zh_text) == []


class TestCrossLanguageLinks:
    @pytest.mark.parametrize("zh", IDS)
    def test_pair_links_both_ways(self, zh: str, pair_texts) -> None:
        en_text, zh_text = pair_texts[zh]
        en_rel = EN_BY_ZH[zh]
        assert _missing_counterpart_link(en_text, zh) == []
        assert _missing_counterpart_link(zh_text, en_rel) == []

    @pytest.mark.parametrize("zh", IDS)
    def test_relative_links_resolve(self, zh: str, pair_texts) -> None:
        if not (ROOT / ".git").exists():
            # An unpacked distribution omits repo scaffolding (the governance docs
            # link into `.github/`), so absence there is a packaging decision, not a
            # dead link; this check guards the version-controlled tree.
            pytest.skip("unpacked distribution tree, not a repo checkout")
        en_text, zh_text = pair_texts[zh]
        en_rel = EN_BY_ZH[zh]
        assert _unresolved_links(en_rel, en_text) == []
        assert _unresolved_links(zh, zh_text) == []


class TestSelfChecks:
    """The guards must actually fire, otherwise the checks above are theatre."""

    EN = "# Title\n\n```bash\nmkdir -p <dir>   # make a directory\n```\n\n## Body\n\ntext\n"

    def test_translated_placeholder_is_caught(self) -> None:
        zh = self.EN.replace("<dir>", "<目录>")
        assert _bad_placeholders(zh) == ["<目录>"]

    def test_placeholder_translated_in_a_comment_is_caught(self) -> None:
        # Comments are dropped by design, so the placeholder rule must still see it.
        zh = self.EN.replace("mkdir -p <dir>", "mkdir -p <目录>")
        assert _bad_placeholders(zh) == ["<目录>"]

    def test_corrupted_code_line_is_caught(self) -> None:
        zh = self.EN.replace("mkdir -p <dir>", "mkdir -p <dir> ; rm -rf /tmp/x")
        problems = _diff_code_blocks(self.EN, zh)
        assert any("Chinese-only code" in p for p in problems)

    def test_translated_comment_is_not_a_defect(self) -> None:
        zh = self.EN.replace("# make a directory", "# 创建目录")
        assert _diff_code_blocks(self.EN, zh) == []

    def test_missing_section_is_caught(self) -> None:
        assert _diff_headings(self.EN, self.EN.replace("## Body", "")) != []

    def test_heading_rename_without_anchor_is_caught(self) -> None:
        toc = "[跳过去](#body)\n\n"
        renamed = self.EN.replace("## Body", "## Body renamed").replace(
            "# Title", "# Title\n\n" + toc
        )
        assert _dead_anchors(renamed) == ["#body"]

    def test_formal_boundary_term_inversion_is_caught(self) -> None:
        assert _bad_boundary_terms("一条 GSSP 定义的边界可以带误差。") != []

    def test_data_model_endpoint_wording_is_allowed(self) -> None:
        assert _bad_boundary_terms("逐边界的误差字段 `uncertainty_ma`。") == []

    def test_dropped_back_link_is_caught(self) -> None:
        assert _missing_counterpart_link("# Title\n\nno links here\n", "x.zh.md") == ["x.zh.md"]
