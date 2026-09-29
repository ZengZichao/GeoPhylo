"""End-to-end: Bio.Phylo timetree with linear geological time axis.

Tests the stable pipeline that requires ``biopython``:
``Phylo.read()`` → ``Phylo.draw()`` → ``spec_from_biophylo()`` →
``add_geo_axis()`` → ``GeoAxisResult.finalize()``.

The Newick tree is a synthetic Triassic–Jurassic ichthyosauriform tree
(root 245 Ma; four genera "extinct" at 225/230/196/155 Ma).  Branch lengths
are in Ma so ``age_conversion=1.0``.  Diachronous tips are intentional —
extinct clades' leaves naturally fall on their stratigraphic ages.
"""

from __future__ import annotations

from io import StringIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

pytest.importorskip("Bio")  # biopython 是可选 extra：未安装时整个模块跳过

from Bio import Phylo

from geophylo import (
    CoordinateError,
    GeoAxisResult,
    Timescale,
    add_geo_axis,
    spec_from_biophylo,
)

NEWICK = """
((Nothosaurus:10.0, Placodus:5.0):10.0,
 (Ichthyosaurus:19.0, Ophthalmosaurus:60.0):30.0);
"""
ROOT_AGE = 245.0


def _draw_tree() -> tuple[plt.Figure, plt.Axes, object]:
    tree = Phylo.read(StringIO(NEWICK), "newick")
    fig, ax = plt.subplots(figsize=(12, 8))
    Phylo.draw(tree, axes=ax, do_show=False)
    return fig, ax, tree


class TestBioPhyloTimetreeE2E:
    """Full Bio.Phylo timetree → geo-axis pipeline."""

    def test_linear_timetree_bottom(self):
        """Standard bottom position with Period + Epoch ranks and boundary ticks."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)
        result = add_geo_axis(
            ax,
            spec=spec,
            position="bottom",
            ranks=["Period", "Epoch"],
            tick_style="boundaries",
        )
        plt.tight_layout()
        result.finalize()

        assert isinstance(result, GeoAxisResult)
        assert result.spec.mode == "root_distance"
        assert result.spec.root_age == ROOT_AGE
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        plt.close(fig)

    def test_linear_timetree_top(self):
        """Top position — time axis still 'x'."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)
        result = add_geo_axis(ax, spec=spec, position="top", ranks=["Period"])
        result.finalize()
        assert result.position == "top"
        plt.close(fig)

    def test_spec_age_range_from_tree_data(self):
        """age_range must be derived from actual branch lengths, not view limits."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)

        # Max root distance = 90 Ma (Ophthalmosaurus: 30+60 via parent).
        # min_age = 245 - 90 = 155; max_age = 245.
        assert spec.age_range[0] == pytest.approx(155.0, abs=1e-9)
        assert spec.age_range[1] == pytest.approx(245.0, abs=1e-9)
        plt.close(fig)

    def test_age_conversion_as_function(self):
        """age_conversion as a callable (e.g. multiply by 2)."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(
            tree,
            ax,
            time_axis="x",
            age_conversion=lambda bl: bl * 2.0,
            root_age=ROOT_AGE,
        )
        # Max root distance doubles: 90 → 180; min_age = 245 - 180 = 65
        assert spec.age_range[0] == pytest.approx(65.0, abs=1e-9)
        plt.close(fig)

    def test_age_conversion_scalar(self):
        """age_conversion as a float multiplier."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(
            tree,
            ax,
            time_axis="x",
            age_conversion=0.5,
            root_age=ROOT_AGE,
        )
        # Max distance halved: 45 → min_age = 245 - 45 = 200
        assert spec.age_range[0] == pytest.approx(200.0, abs=1e-9)
        plt.close(fig)

    def test_nonzero_root_branch_length_rejected(self):
        """Root branch_length non-zero must raise CoordinateError."""
        tree = Phylo.read(StringIO(NEWICK), "newick")
        tree.root.branch_length = 5.0
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="非零"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)
        plt.close(fig)

    def test_unit_depth_fallback_rejected_by_default(self):
        """Tree with all-None branch lengths: rejected unless allow_unit_depth=True."""
        newick_all_none = "((A, B), (C, D));"
        tree = Phylo.read(StringIO(newick_all_none), "newick")
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="等深回退"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=100.0)
        plt.close(fig)

    def test_unit_depth_allowed_with_warning(self):
        """allow_unit_depth=True suppresses the error but warns."""
        newick_all_none = "((A, B), (C, D));"
        tree = Phylo.read(StringIO(newick_all_none), "newick")
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.warns(UserWarning, match="等深回退"):
            spec = spec_from_biophylo(
                tree,
                ax,
                time_axis="x",
                age_conversion=1.0,
                root_age=100.0,
                allow_unit_depth=True,
            )
        # Each branch = 1 → max distance = 2 → min_age = 98
        assert spec.age_range[0] == pytest.approx(98.0, abs=1e-9)
        plt.close(fig)

    def test_single_leaf_tree_rejected(self):
        """Single-leaf tree → max_distance = 0 → CoordinateError."""
        tree = Phylo.read(StringIO("A;"), "newick")
        tree.root.branch_length = None
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="退化为一个点"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=100.0)
        plt.close(fig)

    def test_min_age_negative_rejected(self):
        """root_age too small → min_age < 0 → CoordinateError."""
        tree = Phylo.read(StringIO(NEWICK), "newick")
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="超过 root_age"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=10.0)
        plt.close(fig)

    def test_age_conversion_zero_rejected(self):
        """age_conversion=0.0 → CoordinateError."""
        tree = Phylo.read(StringIO(NEWICK), "newick")
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="正有限值"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=0.0, root_age=245.0)
        plt.close(fig)

    def test_age_conversion_negative_rejected(self):
        """Negative age_conversion → CoordinateError."""
        tree = Phylo.read(StringIO(NEWICK), "newick")
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="正有限值"):
            spec_from_biophylo(tree, ax, time_axis="x", age_conversion=-1.0, root_age=245.0)
        plt.close(fig)

    def test_age_conversion_non_callable_non_number_rejected(self):
        """String age_conversion → CoordinateError."""
        tree = Phylo.read(StringIO(NEWICK), "newick")
        fig, ax = plt.subplots(figsize=(8, 6))
        with pytest.raises(CoordinateError, match="必须是 float 或 callable"):
            spec_from_biophylo(
                tree,
                ax,
                time_axis="x",
                age_conversion="Ma",
                root_age=245.0,  # type: ignore[arg-type]
            )
        plt.close(fig)

    def test_finalized_layout_stable(self):
        """After finalize(), a second draw must not change label diagnostics."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)
        result = add_geo_axis(
            ax,
            spec=spec,
            ranks=["Period", "Epoch"],
            tick_style="boundaries",
        )
        plt.tight_layout()
        result.finalize()
        hidden1 = result.labels_hidden
        fig.canvas.draw()
        assert result.labels_hidden == hidden1
        plt.close(fig)

    def test_inverted_x_axis(self):
        """Host with inverted x-axis (older on left) should still work."""
        fig, ax, tree = _draw_tree()
        ax.set_xlim(250, 180)  # Inverted
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)
        result = add_geo_axis(ax, spec=spec, position="bottom", ranks=["Period"])
        result.finalize()
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        plt.close(fig)

    def test_data_intervals_match_snapshot(self):
        """The intervals drawn on the geo-axis must come from the ICS snapshot."""
        fig, ax, tree = _draw_tree()
        spec = spec_from_biophylo(tree, ax, time_axis="x", age_conversion=1.0, root_age=ROOT_AGE)
        result = add_geo_axis(ax, spec=spec, ranks=["Period"])
        result.finalize()

        ts = Timescale()
        # Check that drawn rectangles' colors match the snapshot
        drawn_colors = set()
        for a in result.artists:
            if type(a).__name__ == "Rectangle":
                import matplotlib.colors

                drawn_colors.add(matplotlib.colors.to_hex(a.get_facecolor()).lower())
        snapshot_colors = {i.color.lower() for i in ts.iter_intervals(ranks=["Period"])}
        # Every drawn color should be in the snapshot
        assert drawn_colors.issubset(snapshot_colors | set()), (
            f"Drawn colors not in snapshot: {drawn_colors - snapshot_colors}"
        )
        plt.close(fig)
