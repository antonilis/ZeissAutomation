"""
IO/read_czi_file.py on a real overview image: tests/fixtures/guv_overview.czi (see the README
there). The metadata read here is all PixelStageConverter receives.
"""
import os

import pytest

pytest.importorskip("pylibCZIrw")  # read_czi_file imports it at the top

from load_module import load  # noqa: E402

reader_module = load("IO/read_czi_file.py", "read_czi_file_under_test")
psc = load("data_processing/image_analysis/pixel_stage_converter.py", "pixel_stage_converter_for_czi")

CZI = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "guv_overview.czi")

STAGE = {"x": 41582.224, "y": 39297.208, "z": 2085.667}
M_PER_PX = 4.1432128906249995e-07


@pytest.fixture(scope="module")
def reader():
    return reader_module.CziFileReader(CZI, analysis_channel=1, extra_channels=[0, 2])


###################### the file is clean ##############################################################


@pytest.mark.parametrize("secret", [b"2871001239", b"2842000204", b"yusufqq", b"C:\\Users", b"D:\\zeiss",
                                    b"<UserName>zeiss"])
def test_fixture_is_scrubbed(secret):
    with open(CZI, "rb") as f:
        assert secret not in f.read()


###################### metadata #######################################################################


def test_scaling_is_in_metres_per_pixel(reader):
    # PixelStageConverter multiplies by 1e6; a value already in um would move the stage by metres
    assert reader.metadata["scaling_um_per_pixel"] == {"X": M_PER_PX, "Y": M_PER_PX}


def test_stage_position(reader):
    assert reader.metadata["stage_position"] == pytest.approx(STAGE)


def test_no_zstack_and_no_tiles(reader):
    assert reader.metadata["z_scan"]["is_activated"] is False
    assert reader.metadata["tiles"] == []


@pytest.mark.xfail(strict=True, reason=(
    "BUG read_czi_file.py:72-89 (_extract_channels): './/{*}Channel' collects every Channel element "
    "of the document (DisplaySetting, every Track, Dimensions), 15 entries for this three-channel "
    "image, and the name is read from a child <Name> element while ZEN stores it in the Name "
    "attribute, so the names are missing. metadata['channels'] is not read anywhere today."))
def test_channels_are_the_channels_of_the_image(reader):
    assert [(c["id"], c["name"]) for c in reader.metadata["channels"]] == [
        ("Channel:0", "AF488"), ("Channel:1", "RhodB"), ("Channel:2", "T-PMT")]


###################### pixels #########################################################################


def test_every_requested_channel_is_read(reader):
    assert sorted(reader.channels_data) == [0, 1, 2]
    assert {c: a.shape for c, a in reader.channels_data.items()} == {0: (512, 512), 1: (512, 512), 2: (512, 512)}
    assert reader.czi_file is reader.channels_data[1]


def test_channels_hold_different_images(reader):
    assert (reader.channels_data[0] != reader.channels_data[1]).any()
    assert (reader.channels_data[1] != reader.channels_data[2]).any()


###################### into the converter #############################################################


def test_image_centre_is_the_stage_position(reader):
    # 512 px: the centre lies between pixels 255 and 256
    converter = psc.PixelStageConverter(reader.metadata, reader.czi_file.shape)

    assert converter.convert_xy([255.5, 255.5]) == pytest.approx((STAGE["x"], STAGE["y"]))


def test_image_corners_span_the_field_of_view(reader):
    converter = psc.PixelStageConverter(reader.metadata, reader.czi_file.shape)
    left, top = converter.convert_xy([0.0, 0.0])
    right, bottom = converter.convert_xy([511.0, 511.0])

    assert right - left == pytest.approx(511 * M_PER_PX * 1e6)
    assert bottom - top == pytest.approx(511 * M_PER_PX * 1e6)
