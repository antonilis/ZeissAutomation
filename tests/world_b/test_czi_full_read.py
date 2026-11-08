"""
IO/read_czi_file.py on acquisitions that are not in the repository: a Z stack, a tiled image and
the FRAP probe, whose stage geometry ZEN reported itself.

Point ZEISS_TEST_DATA at the folder that holds them; without it every test here is skipped:

    ZEISS_TEST_DATA=/media/dysk/MPI .venv/bin/python -m pytest -m data
"""
import json
import os

import pytest

pytest.importorskip("pylibCZIrw")

from load_module import load  # noqa: E402

pytestmark = pytest.mark.data

reader_module = load("DecisionEngine/IO/read_czi_file.py", "read_czi_file_full_read")
psc = load("DecisionEngine/data_processing/image_analysis/pixel_stage_converter.py", "pixel_stage_converter_full_read")

ZSTACK = ("data/I_visit/adaptive_zsan_GUV/results/obj_129cb88f-ae68-4848-af9b-0d2229a214ed/"
          "129cb88f-ae68-4848-af9b-0d2229a214ed_GUV_automation_RhB_zStack_image_reanalysis_z.czi")
TILES = "results/SLBs_40x_A655_1proc_mol/results/C10/C10_SLB_A655_zscan_reanalysis_z.czi"
FRAP = "results/FRAP_probe_20260930_175902"


def data_path(relative):
    root = os.environ.get("ZEISS_TEST_DATA")
    if not root:
        pytest.skip("ZEISS_TEST_DATA is not set")
    path = os.path.join(root, relative)
    if not os.path.exists(path):
        pytest.skip("{} is not in ZEISS_TEST_DATA".format(relative))
    return path


def read(relative, **kwargs):
    return reader_module.CziFileReader(data_path(relative), analysis_channel=0, **kwargs)


###################### Z stack ########################################################################


def test_zstack_metadata():
    meta = read(ZSTACK).metadata

    assert meta["z_scan"]["is_activated"] is True
    assert meta["scaling_um_per_pixel"]["Z"] == pytest.approx(2.7e-07)
    assert meta["stage_position"] == pytest.approx({"x": 41599.151, "y": 39234.142, "z": 2085.667})
    assert meta["tiles"] == []


def test_zstack_is_read_as_a_stack_of_both_channels():
    reader = read(ZSTACK, extra_channels=[1])

    assert {c: a.shape for c, a in reader.channels_data.items()} == {0: (46, 512, 512), 1: (46, 512, 512)}


###################### tiles ##########################################################################


def test_tiles_are_p1_to_p21_at_the_stage_xy_stepping_in_z():
    meta = read(TILES).metadata
    tiles = meta["tiles"]
    z = [t["z"] for t in tiles]

    assert [t["name"] for t in tiles] == ["P{}".format(i) for i in range(1, 22)]
    assert {(t["x"], t["y"]) for t in tiles} == {(meta["stage_position"]["x"], meta["stage_position"]["y"])}
    assert z == sorted(z) and len(set(z)) == len(z)
    assert meta["z_scan"]["is_activated"] is False


def test_tiles_are_read_as_one_plane_per_tile_and_give_their_z():
    reader = read(TILES)
    converter = psc.PixelStageConverter(reader.metadata, reader.czi_file.shape)

    assert reader.czi_file.shape == (21, 1633, 1633)
    # plane k of the stack is tile P(k+1)
    assert converter.convert_z_auto([0.0, 0.0, 4.0]) == reader.metadata["tiles"][4]["z"]


###################### FRAP probe: geometry reported by ZEN ##########################################


def test_frap_probe_geometry_on_every_field():
    # For each of the three reference images ZEN reported both the stage position and the top left
    # corner of the image; the converter must turn pixel (0, 0) into that corner
    folder = data_path(FRAP)
    with open(os.path.join(folder, "frap_probe.json")) as f:
        probe = json.load(f)
    files = {1: "field1_pixels_reference.czi", 2: "field2_um_from_top_left_reference.czi",
             3: "field3_stage_um_reference.czi"}

    for field in probe:
        reader = reader_module.CziFileReader(os.path.join(folder, files[field["field"]]), analysis_channel=0)
        converter = psc.PixelStageConverter(reader.metadata, reader.czi_file.shape)
        stage = reader.metadata["stage_position"]

        assert [stage["x"], stage["y"], stage["z"]] == pytest.approx(field["stage"])
        assert converter.convert_xy([0.0, 0.0]) == pytest.approx(tuple(field["reference"]["left_top"]), abs=1e-6)
