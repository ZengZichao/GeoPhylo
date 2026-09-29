"""End-to-end: circular tree with polar geological time ring (experimental).

Tests the experimental pipeline that requires ``biopython`` + ``numpy``:
``radial_spec_from_biophylo()`` → manual tree drawing → ``add_geo_ring()``.

The tree is the same synthetic Triassic–Jurassic ichthyosauriform tree used in
the linear timetree tests.  The circular recipe follows the documented pattern
in ``examples/circular_tree.py`` (spec 6.3).
"""

from __future__ import annotations

import math
from io import StringIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

pytest.importorskip("Bio")  # biopython 是可选 extra：未安装时整个模块跳过

from Bio import Phylo

from geophylo import (
    AxesTypeError,
    CoordinateError,
    GeoAxisResult,
    InvalidRadiusError,
    add_geo_ring,
)
from geophylo.adapter import radial_spec_from_biophylo
from geophylo.coordinate.radial import RadialSpec

pytestmark = pytest.mark.experimental

NEWICK = """
((Nothosaurus:10.0, Placodus:5.0):10.0,
 (Ichthyosaurus:19.0, Ophthalmosaurus:60.0):30.0);
"""
ROOT_AGE = 245.0


def _tree():
    return Phylo.read(StringIO(NEWICK), "newick")


def _full_radial(tree=None, **kwargs):
    """A RadialSpec covering the full circle."""
    tree = tree or _tree()
    defaults = dict(
        age_conversion=1.0,
        root_age=ROOT_AGE,
        r_inner=0.0,
        r_outer=1.0,
        theta_range=(0.0, 2.0 * math.pi),
    )
    defaults.update(kwargs)
    return radial_spec_from_biophylo(tree, **defaults)


class TestCircularTreeE2E:
    """Full circular tree → geo-ring pipeline."""

    def test_ring_on_polar_axes(self):
        """Basic ring on polar axes with default band."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        result = add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
        assert isinstance(result, GeoAxisResult)
        assert result.host_ax is ax
        assert result.geo_ax is ax
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) > 0
        plt.close(fig)

    def test_non_polar_axes_rejected(self):
        """Cartesian Axes must be rejected."""
        fig, ax = plt.subplots(figsize=(6, 4))
        radial = _full_radial()
        with pytest.raises(AxesTypeError, match="极坐标"):
            add_geo_ring(ax, spec=radial, rank="Period")
        plt.close(fig)

    def test_ring_quarter_circle(self):
        """Partial circle (π/2) — every segment width must equal π/2."""
        tree = _tree()
        radial = radial_spec_from_biophylo(
            tree,
            age_conversion=1.0,
            root_age=ROOT_AGE,
            r_inner=0.0,
            r_outer=1.0,
            theta_range=(0.0, math.pi / 2),
        )
        fig = plt.figure(figsize=(6, 6))
        ax = fig.add_subplot(111, projection="polar")
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.9, 1.0))
        widths = [p.get_width() for p in ax.patches]
        assert widths
        assert all(math.isclose(w, math.pi / 2, abs_tol=1e-9) for w in widths)
        plt.close(fig)

    def test_band_inside_rlim(self):
        """Band outside the rlim must be rejected, and rlim must not change."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        ax.set_rlim(0.0, 0.5)
        rlim_before = ax.get_ylim()
        with pytest.raises(InvalidRadiusError, match="rlim"):
            add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
        assert ax.get_ylim() == rlim_before
        plt.close(fig)

    def test_band_data_unit(self):
        """band_unit='data' with explicit rlim."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        ax.set_rlim(0.0, 20.0)
        radial = RadialSpec(
            age_range=(0.0, 300.0),
            radius_range=(10.0, 20.0),
            theta_range=(0.0, math.pi),
        )
        add_geo_ring(ax, spec=radial, rank="Period", band=(12.0, 16.0), band_unit="data")
        spans = [(p.get_y(), p.get_y() + p.get_height()) for p in ax.patches]
        assert spans
        assert all(lo >= 12.0 - 1e-12 for lo, _ in spans)
        assert all(hi <= 16.0 + 1e-12 for _, hi in spans)
        plt.close(fig)

    def test_full_recipe_tree_and_ring_aligned(self):
        """Full recipe: tree + ring share the same RadialSpec instance."""
        tree = _tree()
        radial = radial_spec_from_biophylo(
            tree,
            age_conversion=1.0,
            root_age=ROOT_AGE,
            r_inner=0.0,
            r_outer=1.0,
            theta_range=(0.0, math.pi / 2),
        )
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")

        # Tree layout: leaves evenly spaced
        theta_0, theta_1 = radial.theta_range
        leaves = tree.get_terminals()
        theta = {
            id(leaf): theta_0 + (theta_1 - theta_0) * i / (len(leaves) - 1)
            for i, leaf in enumerate(leaves)
        }
        radius = {}
        node_ages = []
        for clade in tree.find_clades(order="postorder"):
            age = radial.root_age - tree.distance(clade)
            node_ages.append((clade, age))
            radius[id(clade)] = radial.age_to_radius(age)
            if clade.clades:
                theta[id(clade)] = float(np.mean([theta[id(c)] for c in clade.clades]))

        for clade in tree.find_clades():
            for child in clade.clades:
                ax.plot(
                    [theta[id(clade)], theta[id(child)]],
                    [radius[id(clade)], radius[id(child)]],
                    color="black",
                    lw=0.8,
                )
        ax.set_axis_off()

        result = add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
        assert isinstance(result, GeoAxisResult)

        # Consistency: radius → age → radius round-trip
        for clade, age in node_ages:
            r = radius[id(clade)]
            recovered_age = radial.radius_to_age(r)
            assert recovered_age == pytest.approx(age, abs=1e-9)
        plt.close(fig)

    def test_ring_with_labels(self):
        """Ring with labels=True should produce visible Text artists."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        result = add_geo_ring(
            ax,
            spec=radial,
            rank="Period",
            band=(0.9, 1.0),
            label=True,
            label_size=5.0,
        )
        texts = [a for a in result.artists if type(a).__name__ == "Text" and a.get_text()]
        assert len(texts) > 0
        plt.close(fig)

    def test_ring_rotate_labels(self):
        """rotate_labels=True: rotation should match theta_center."""
        tree = _tree()
        radial = radial_spec_from_biophylo(
            tree,
            age_conversion=1.0,
            root_age=ROOT_AGE,
            r_inner=0.0,
            r_outer=1.0,
            theta_range=(0.0, math.pi / 3),
        )
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        result = add_geo_ring(
            ax,
            spec=radial,
            rank="Period",
            rotate_labels=True,
        )
        texts = [t for t in result.artists if type(t).__name__ == "Text" and t.get_text()]
        assert texts
        theta_center = (0.0 + math.pi / 3) / 2.0
        expected_rotation = math.degrees(theta_center)
        for t in texts:
            assert float(t.get_rotation()) == pytest.approx(expected_rotation, abs=1e-9)
        plt.close(fig)

    def test_ring_update_band(self):
        """update() with new band should move the ring."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        result = add_geo_ring(ax, spec=radial, rank="Period", key="ring", band=(0.9, 1.0))
        before = [(p.get_y(), p.get_height()) for p in ax.patches]
        result.update(band=(0.1, 0.2))
        after = [(p.get_y(), p.get_height()) for p in ax.patches]
        assert before != after
        # New band should be inside [0.1, 0.2]
        for y, h in after:
            assert y >= 0.1 - 1e-12
            assert y + h <= 0.2 + 1e-12
        plt.close(fig)

    def test_ring_idempotent_key(self):
        """Same key + same spec → same result, rebuilt artists."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        r1 = add_geo_ring(ax, spec=radial, rank="Period", key="ring", band=(0.9, 1.0))
        n_before = len(r1.artists)
        r2 = add_geo_ring(ax, spec=radial, rank="Period", key="ring", band=(0.8, 1.0))
        assert r2 is r1
        # Same count (rebuilt in place)
        assert len(r2.artists) == n_before
        plt.close(fig)

    def test_no_rlim_modification(self):
        """add_geo_ring must never call set_rlim or set_rorigin."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()

        def _forbidden(*args, **kwargs):
            raise AssertionError("set_rlim/set_rorigin must not be called")

        ax.set_rlim = _forbidden  # type: ignore[method-assign]
        ax.set_rorigin = _forbidden  # type: ignore[method-assign]
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.92, 1.0))
        plt.close(fig)

    def test_narrow_window_does_not_rescale(self):
        """Window only clips which intervals are drawn; does not rescale radii."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = RadialSpec(
            age_range=(0.0, 300.0),
            radius_range=(0.0, 1.0),
            theta_range=(0.0, math.pi),
        )
        add_geo_ring(ax, spec=radial, rank="Period", band=(0.0, 1.0), min_age=0.0, max_age=100.0)
        spans = [(p.get_y(), p.get_y() + p.get_height()) for p in ax.patches]
        # The youngest boundary (0 Ma) maps to r=1.0 (outermost)
        assert max(hi for _, hi in spans) == pytest.approx(1.0, abs=1e-12)
        plt.close(fig)

    def test_nonzero_root_branch_length_rejected(self):
        """Root branch_length non-zero must be rejected."""
        tree = _tree()
        tree.root.branch_length = 5.0
        fig = plt.figure(figsize=(6, 6))
        fig.add_subplot(111, projection="polar")
        with pytest.raises(CoordinateError):
            radial_spec_from_biophylo(
                tree,
                age_conversion=1.0,
                root_age=ROOT_AGE,
                r_inner=0.0,
                r_outer=1.0,
                theta_range=(0.0, 1.0),
            )
        plt.close(fig)

    def test_multi_rank_rejected(self):
        """rank must be a single string, not a sequence."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        with pytest.raises(Exception):  # InvalidRankError
            add_geo_ring(ax, spec=radial, rank=["Period", "Epoch"])  # type: ignore[arg-type]
        plt.close(fig)

    def test_fill_false_no_rectangles(self):
        """fill=False on a ring produces no Rectangle patches."""
        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, projection="polar")
        radial = _full_radial()
        result = add_geo_ring(ax, spec=radial, rank="Period", fill=False)
        rects = [a for a in result.artists if type(a).__name__ == "Rectangle"]
        assert len(rects) == 0
        plt.close(fig)
