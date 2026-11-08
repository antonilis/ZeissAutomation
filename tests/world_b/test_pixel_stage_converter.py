"""
PixelStageConverter turns pixel positions found by an analyser into stage micrometres. The
macro drives the stage to whatever comes out of it, so an error here sends the objective to
the wrong place.

Pixel positions are [column, row(, z)]: circles (cv2 moments), cellpose ([centroid-1,
centroid-0]) and hexagonal_mesh (cv2 centroids) all write them in that order.
"""
import copy

import pytest

from load_module import load

psc = load("DecisionEngine/data_processing/image_analysis/pixel_stage_converter.py", "pixel_stage_converter_under_test")
PixelStageConverter = psc.PixelStageConverter


def metadata(x=100.0, y=200.0, z=50.0, um_per_px=1.0, z_um=0.5, z_scan=None, tiles=None):
    return {
        "stage_position": {"x": x, "y": y, "z": z},
        # the .czi stores the scaling in metres per pixel
        "scaling_um_per_pixel": {"X": um_per_px * 1e-6, "Y": um_per_px * 1e-6, "Z": z_um * 1e-6},
        "z_scan": z_scan,
        "tiles": tiles or [],
    }


def xy(converter, column, row):
    return converter.convert_xy([float(column), float(row)])


###################### X and Y ########################################################################


def test_center_pixel_maps_to_stage_position():
    converter = PixelStageConverter(metadata(), (5, 5))

    assert xy(converter, 2, 2) == pytest.approx((100.0, 200.0))


@pytest.mark.parametrize("step, expected", [
    ((1, 0), (102.0, 200.0)),  # one column to the right moves X only
    ((0, 1), (100.0, 202.0)),  # one row down moves Y only
])
def test_one_pixel_step_is_scaling_in_um(step, expected):
    converter = PixelStageConverter(metadata(um_per_px=2.0), (5, 5))

    assert xy(converter, 2 + step[0], 2 + step[1]) == pytest.approx(expected)


def test_top_left_pixel_matches_zen_left_top():
    # Values from a real run, results/FRAP_probe_20260930_175902/frap_probe.json, field 1:
    # ZEN put the stage at (18587.1, 462.8) and reported the top left of the 1633 x 1633 image,
    # at 0.12990355174525411 um/px, as (18481.098701775871, 356.79870177587264).
    converter = PixelStageConverter(metadata(x=18587.1, y=462.8, um_per_px=0.12990355174525411), (1633, 1633))

    assert xy(converter, 0, 0) == pytest.approx((18481.098701775871, 356.79870177587264), abs=1e-6)


def test_center_mode_returns_stage_xy():
    converter = PixelStageConverter(metadata(), (5, 5))

    assert converter.convert_xy([0.0, 4.0], mode="center") == (100.0, 200.0)


def test_unknown_xy_mode_raises():
    converter = PixelStageConverter(metadata(), (5, 5))

    with pytest.raises(ValueError):
        converter.convert_xy([0.0, 0.0], mode="left")


###################### a non-square image #############################################################
# 4 rows by 6 columns at 1 um/px around stage (0, 0). The top left pixel, column 0 row 0, is
# 2.5 um left of the centre and 1.5 um above it.


def test_rectangular_image_current_behaviour():
    # CURRENT BEHAVIOUR, frozen. convert_xy centres the column on H and the row on W, so on a
    # non-square image every position is off by (W - H) / 2 pixels. Remove this test together
    # with the xfail below once convert_xy is fixed.
    converter = PixelStageConverter(metadata(x=0.0, y=0.0), (4, 6))

    assert xy(converter, 0, 0) == pytest.approx((-1.5, -2.5))


@pytest.mark.xfail(strict=True, reason=(
    "BUG pixel_stage_converter.py:82-83: the column (px[0]) is centred on H/2 and the row "
    "(px[1]) on W/2; it should be W/2 and H/2. Invisible on square images, off by (W - H) / 2 "
    "pixels on any other."))
def test_rectangular_image_x_uses_width():
    converter = PixelStageConverter(metadata(x=0.0, y=0.0), (4, 6))

    assert xy(converter, 0, 0) == pytest.approx((-2.5, -1.5))
    assert xy(converter, 5, 3) == pytest.approx((2.5, 1.5))


###################### image shape ####################################################################


@pytest.mark.parametrize("shape, expected", [((4, 6), (4, 6)), ((9, 4, 6), (4, 6))])
def test_image_shape_normalisation(shape, expected):
    assert PixelStageConverter(metadata(), shape).image_shape == expected


def test_four_dimensional_image_raises():
    with pytest.raises(ValueError):
        PixelStageConverter(metadata(), (1, 2, 4, 6))


###################### Z ##############################################################################


def test_z_no_transform():
    assert psc.z_no_transform([1.0, 2.0, 3.0], {"z": 50.0}, {"Z": 0.5e-6}, {}) == 50.0


@pytest.mark.parametrize("px, expected", [([1.0, 2.0, 4.0], 52.0), ([1.0, 2.0], 50.0)])
def test_z_normal_with_and_without_z_index(px, expected):
    assert psc.z_normal(px, {"z": 50.0}, {"Z": 0.5e-6}, {}) == pytest.approx(expected)


def test_convert_z_auto_uses_zscan_when_activated():
    converter = PixelStageConverter(metadata(z_scan={"is_activated": True, "is_center_mode": True}), (5, 5))

    assert converter.convert_z_auto([2.0, 2.0, 3.0]) == pytest.approx(51.5)


@pytest.mark.parametrize("z_index, expected", [(2.0, 77.0), (5.0, 50.0)])
def test_convert_z_auto_uses_tile_lookup(z_index, expected):
    # "Tile 3" is the third tile, index 2; an index with no tile falls back to the stage Z
    tiles = [{"name": "Tile 3", "x": 0.0, "y": 0.0, "z": 77.0}]
    converter = PixelStageConverter(metadata(tiles=tiles), (5, 5))

    assert converter.convert_z_auto([2.0, 2.0, z_index]) == expected


def test_convert_z_auto_fallback_to_stage_z():
    converter = PixelStageConverter(metadata(z_scan={"is_activated": False, "is_center_mode": False}), (5, 5))

    assert converter.convert_z_auto([2.0, 2.0]) == 50.0


###################### convert_points #################################################################


def test_ids_and_properties_survive_input_not_mutated():
    converter = PixelStageConverter(metadata(), (5, 5))
    points = [{"id": "a-1", "position": [2, 2], "radius": 7}, {"id": "b-2", "position": [3, 2], "radius": 9}]
    before = copy.deepcopy(points)

    result = converter.convert_points(points, z_strategy=psc.z_no_transform)

    assert points == before
    assert [p["id"] for p in result] == ["a-1", "b-2"]
    assert [p["radius"] for p in result] == [7, 9]
    assert result[0]["position"] == pytest.approx([100.0, 200.0, 50.0])
    assert result[1]["position"] == pytest.approx([101.0, 200.0, 50.0])


def test_convert_points_accepts_a_converter_method():
    converter = PixelStageConverter(metadata(z_scan={"is_activated": True, "is_center_mode": True}), (5, 5))

    result = converter.convert_points([{"id": "a", "position": [2, 2, 2]}], z_strategy=converter.convert_z_auto)

    assert result[0]["position"] == pytest.approx([100.0, 200.0, 51.0])


@pytest.mark.parametrize("strategy", [None, "z_normal"])
def test_missing_or_non_callable_z_strategy_raises(strategy):
    converter = PixelStageConverter(metadata(), (5, 5))

    with pytest.raises(ValueError):
        converter.convert_points([{"id": "a", "position": [2, 2]}], z_strategy=strategy)


@pytest.mark.xfail(strict=True, reason=(
    "BUG pixel_stage_converter.py:141-145: convert_points catches every TypeError raised by a "
    "one-argument strategy and calls it again with four arguments, so a real TypeError inside "
    "the strategy is replaced by a misleading 'takes 1 positional argument but 4 were given'."))
def test_type_error_inside_strategy_not_masked():
    converter = PixelStageConverter(metadata(), (5, 5))

    def strategy(px):
        raise TypeError("boom inside the strategy")

    with pytest.raises(TypeError, match="boom inside the strategy"):
        converter.convert_points([{"id": "a", "position": [2, 2]}], z_strategy=strategy)
