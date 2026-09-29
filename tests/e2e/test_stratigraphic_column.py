"""End-to-end: stratigraphic column with absolute-age mode.

Tests the simplest full pipeline that requires no external tree library:
``CoordinateSpec.absolute()`` → ``add_geo_axis()`` → ``GeoAxisResult`` lifecycle.

The real data is the ICS 2026/06 geological timescale snapshot bundled with the
package.  The synthetic sea-level curve is purely a vehicle for exercising the
host Axes; the scientific assertions are about the geo-axis overlay, not the curve.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from geophylo import CoordinateSpec, GeoAxisResult, Timescale, add_geo_axis, remove_all
from geophylo.render.linear import RANK_WEIGHTS

# ---------------------------------------------------------------------------
# Real data: ICS intervals from the bundled snapshot
# ---------------------------------------------------------------------------


def _real_periods() -> list[str]:
    """Period-level intervals from the baseline snapshot."""
    ts = Timescale()
    return [i.name for i in ts.iter_intervals(ranks=["Period"])]


def _real_epochs() -> list[str]:
    ts = Timescale()
    return [i.name for i in ts.iter_intervals(ranks=["Epoch"])]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStratigraphicColumnE2E:
    """Full pipeline: synthetic data + absolute-age geo-axis overlay."""

    def test_column_bottom_position_with_all_ranks(self):
        """Bottom position, all five ranks, ages tick style, finalize."""
        window_min, window_max = 0.0, 541.0
        ages = np.linspace(window_min + 2, window_max - 2, 80)
        rng = np.random.default_rng(42)
        values = 60 + 25 * np.sin(ages / 25.0) + rng.normal(0, 3, ages.size)

        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(ages, values, color="0.2", lw=0.8)
        ax.fill_between(ages, 0, values, color="0.85")
        ax.set_xlim(window_max, window_min)  # older on the left
        ax.set_ylim(0, 100)

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(window_min, window_max))
        result = add_geo_axis(
            ax,
            spec=spec,
            position="bottom",
            ranks=["Eon", "Era", "Period", "Epoch", "Age"],
            tick_style="ages",
            tick_max_count=15,
        )
        plt.tight_layout()
        result.finalize()

        assert isinstance(result, GeoAxisResult)
        assert result.spec is spec
        assert result.position == "bottom"
        # At least some rectangles must have been drawn
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        # The "Ma" unit label must be present
        texts = [a for a in result.artists if type(a).__name__ == "Text"]
        assert any(t.get_text() == "Ma" for t in texts)
        plt.close(fig)

    def test_column_top_position_with_two_ranks(self):
        """Top position, Period + Epoch, boundaries tick style."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot([0, 100, 200, 300], [1, 2, 1.5, 3])
        ax.set_xlim(300, 0)

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 300.0))
        result = add_geo_axis(
            ax,
            spec=spec,
            position="top",
            ranks=["Period", "Epoch"],
            tick_style="boundaries",
        )
        result.finalize()

        assert result.position == "top"
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        plt.close(fig)

    def test_column_left_position_vertical(self):
        """Left position (vertical axis), single rank."""
        fig, ax = plt.subplots(figsize=(6, 10))
        ax.set_ylim(541, 0)
        ax.set_xlim(0, 10)

        spec = CoordinateSpec.absolute(time_axis="y", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, position="left", ranks=["Period"])
        result.finalize()

        assert result.position == "left"
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        # In vertical mode, rectangles span the full width (x ∈ [0, 1])
        for r in rects:
            assert r.get_width() == pytest.approx(1.0)
        plt.close(fig)

    def test_column_right_position_vertical(self):
        """Right position (vertical axis), two ranks."""
        fig, ax = plt.subplots(figsize=(6, 10))
        ax.set_ylim(541, 0)
        ax.set_xlim(0, 10)

        spec = CoordinateSpec.absolute(time_axis="y", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, position="right", ranks=["Era", "Period"])
        result.finalize()

        assert result.position == "right"
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        plt.close(fig)

    def test_window_clipping_phanerozoic_only(self):
        """Only Phanerozoic (0–541 Ma) window: Ediacaran should be clipped."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"], min_age=0.0, max_age=541.0)
        result.finalize()

        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        # Every rectangle must fall within [0, 541]
        for r in rects:
            x0 = min(r.get_x(), r.get_x() + r.get_width())
            x1 = max(r.get_x(), r.get_x() + r.get_width())
            assert x0 >= 0.0 - 1e-9
            assert x1 <= 541.0 + 1e-9
        plt.close(fig)

    def test_narrow_window_only_cenozoic(self):
        """Narrow window 0–66 Ma: only Cenozoic periods should appear."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(66, 0)

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 66.0))
        result = add_geo_axis(
            ax,
            spec=spec,
            ranks=["Period", "Epoch"],
            min_age=0.0,
            max_age=66.0,
        )
        result.finalize()

        # The rectangles correspond to intervals; we check that all fall in [0, 66]
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        for r in rects:
            x0 = min(r.get_x(), r.get_x() + r.get_width())
            x1 = max(r.get_x(), r.get_x() + r.get_width())
            assert x0 >= 0.0 - 1e-9
            assert x1 <= 66.0 + 1e-9
        assert len(rects) > 0
        plt.close(fig)

    def test_fill_false_no_rectangles(self):
        """fill=False: no Rectangle patches, but borders and labels may remain."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"], fill=False, border="both")
        result.finalize()

        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) == 0
        # Borders are Line2D
        lines = [a for a in result.artists if type(a).__name__ == "Line2D"]
        assert len(lines) > 0
        plt.close(fig)

    def test_label_skip(self):
        """skip=["Quaternary"] should prevent that name from appearing."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(
            ax,
            spec=spec,
            ranks=["Period"],
            skip=["Quaternary"],
        )
        result.finalize()

        texts = [a for a in result.artists if type(a).__name__ == "Text"]
        visible_texts = [t.get_text() for t in texts if t.get_visible() and t.get_text() != "Ma"]
        assert "Quaternary" not in visible_texts
        plt.close(fig)

    def test_remove_all_cleans_up(self):
        """remove_all should remove every track and return the count."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))

        add_geo_axis(ax, spec=spec, key="track1", ranks=["Period"])
        add_geo_axis(ax, spec=spec, key="track2", ranks=["Era"])
        count = remove_all(ax)
        assert count == 2
        # Second call returns 0
        assert remove_all(ax) == 0
        plt.close(fig)

    def test_update_ranks_in_place(self):
        """update() with new ranks should rebuild without stacking artists."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))

        result = add_geo_axis(ax, spec=spec, key="k", ranks=["Period"])
        n_before = len(result.artists)
        result.update(ranks=["Era"])
        n_after = len(result.artists)
        assert n_after > 0
        # Era has fewer intervals than Period, so artist count should differ
        assert n_after != n_before
        plt.close(fig)

    def test_host_state_preserved(self):
        """Host Axes limits must be unchanged after add_geo_axis."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)
        ax.set_ylim(0, 10)
        xlim_before = ax.get_xlim()
        ylim_before = ax.get_ylim()

        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        add_geo_axis(ax, spec=spec, ranks=["Period"])
        assert ax.get_xlim() == xlim_before
        assert ax.get_ylim() == ylim_before
        plt.close(fig)

    def test_sync_after_xlim_change(self):
        """sync() must realign the track to the new host limits."""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.set_xlim(541, 0)
        spec = CoordinateSpec.absolute(time_axis="x", age_range=(0.0, 541.0))
        result = add_geo_axis(ax, spec=spec, ranks=["Period"])

        ax.set_xlim(300.0, 0.0)
        result.sync()
        assert result.geo_ax.get_xlim() == ax.get_xlim()
        plt.close(fig)

    def test_all_rank_weights_present(self):
        """RANK_WEIGHTS must have entries for all five core ranks."""
        from geophylo.validation import CORE_RANKS

        for rank in CORE_RANKS:
            assert rank in RANK_WEIGHTS, f"Missing weight for rank {rank!r}"
