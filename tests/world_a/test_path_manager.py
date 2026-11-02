"""
PathManager builds every result and temp path of a run. Two points of one run are told apart
only by these paths, so two different points must never get the same one.

Paths are Windows paths built by the fake System.IO (ntpath), as on the microscope PC.
"""
import types

import pytest

from zen_lib.path_manager_main_macro import PathManager

RESULTS = "D:\\automation\\results"
MEASUREMENTS = "D:\\automation\\temp"
ANALYSIS = "D:\\automation\\image_for_analysis"
ZEISS_TEMP = "D:\\zeiss\\Pictures"

UUID = "2fb6a1ba-0dc4-4886-aebd-a465e2a61fee"


@pytest.fixture
def pm():
    config = types.SimpleNamespace(results=RESULTS, measurements=MEASUREMENTS,
                                   analysis=ANALYSIS, zeiss_temp=ZEISS_TEMP)
    return PathManager(config)


###################### overview_image_path ############################################################


def test_overview_image_path_with_name(pm):
    assert pm.overview_image_path(UUID, "A1") == ANALYSIS + "\\A1_" + UUID + "_Image_overview.czi"


def test_overview_image_path_without_name(pm):
    assert pm.overview_image_path(UUID) == ANALYSIS + "\\" + UUID + "_Image_overview.czi"


###################### temp_file_path #################################################################


@pytest.mark.parametrize("reanalysis_type, suffix", [
    (None, "measurements_points.json"),
    ("xy", "measurements_points_reanalysis_xy.json"),
    ("z", "measurements_points_reanalysis_z.json"),
    ("overview_points", "points_for_overview.json"),
])
def test_temp_file_path_suffix_per_type(pm, reanalysis_type, suffix):
    assert pm.temp_file_path(UUID, reanalysis_type, "A1") == MEASUREMENTS + "\\A1_" + UUID + "_" + suffix


def test_temp_file_path_unknown_type_raises(pm):
    with pytest.raises(ValueError, match="Unknown reanalysis type"):
        pm.temp_file_path(UUID, "xyz")


###################### an empty name is no name #######################################################


def test_empty_name_means_no_name(pm):
    assert pm.overview_image_path(UUID, "") == pm.overview_image_path(UUID, None)
    assert pm.temp_file_path(UUID, "xy", "") == pm.temp_file_path(UUID, "xy", None)
    assert pm.result_dir(UUID, None, "") == pm.result_dir(UUID, None, None)
    assert pm.result_path(UUID, "_post", "exp", "") == pm.result_path(UUID, "_post", "exp", None)


###################### result_dir #####################################################################


def test_result_dir_with_obj_id(pm, zen_disk):
    folder = pm.result_dir(UUID, None, "A1")

    assert folder == RESULTS + "\\A1\\obj_" + UUID
    assert zen_disk.has_dir(folder)


@pytest.mark.parametrize("name, expected", [
    ("A1", RESULTS + "\\A1"),
    (None, RESULTS),
])
def test_result_dir_without_obj_id(pm, zen_disk, name, expected):
    # obj_id is None when object finding is off: no obj_ folder, the point name tells results apart
    folder = pm.result_dir(None, None, name)

    assert folder == expected
    assert zen_disk.has_dir(folder)


def test_result_dir_is_idempotent(pm):
    assert pm.result_dir(UUID, None, "A1") == pm.result_dir(UUID, None, "A1")


###################### result_path ####################################################################


def test_result_path_matches_real_slb_naming(pm):
    # A file of this name and place exists from a real run: results\D4\D4_SLB_A655_imaging_post.czi
    assert pm.result_path(None, "_post", "SLB_A655_imaging", "D4") == \
        RESULTS + "\\D4\\D4_SLB_A655_imaging_post.czi"


def test_result_path_matches_real_guv_naming(pm):
    # A file of this name and place exists from a real run, made with no point name:
    # results\obj_<uuid>\<uuid>_GUV_automation_RhB_Atto488_10x_close_up_exp.czi
    assert pm.result_path(UUID, "_exp", "GUV_automation_RhB_Atto488_10x_close_up") == \
        RESULTS + "\\obj_" + UUID + "\\" + UUID + "_GUV_automation_RhB_Atto488_10x_close_up_exp.czi"


def test_result_path_stage_none_has_no_suffix(pm):
    assert pm.result_path(UUID, None, "exp", "A1") == RESULTS + "\\A1\\obj_" + UUID + "\\A1_" + UUID + "_exp.czi"


def test_name_with_spaces_kept_verbatim(pm, zen_disk):
    path = pm.result_path(None, "_post", "imaging", "my sample 1")

    assert path == RESULTS + "\\my sample 1\\my sample 1_imaging_post.czi"
    assert zen_disk.has_dir(RESULTS + "\\my sample 1")


@pytest.mark.parametrize("first, second", [
    # (obj_id, stage, measurement, name) of two different points of one run
    ((None, "_post", "imaging", "A1"), (None, "_post", "imaging", "A10")),
    ((None, "_post", "imaging", "r1c1"), (None, "_post", "imaging", "r1c10")),
    # the same joined file name, "A1_B_exp", but different points
    ((None, None, "B_exp", "A1"), (None, None, "exp", "A1_B")),
    ((UUID, "_exp", "imaging", "A1"), ("other-" + UUID, "_exp", "imaging", "A1")),
])
def test_distinct_points_never_collide(pm, first, second):
    assert pm.result_path(*first) != pm.result_path(*second)


###################### get_latest_fcs_and_raws ########################################################


def test_latest_fcs_and_matching_raws(pm, zen_disk):
    zen_disk.write_file(ZEISS_TEMP + "\\old.fcs", mtime=1)
    zen_disk.write_file(ZEISS_TEMP + "\\old_R1.raw", mtime=1)
    zen_disk.write_file(ZEISS_TEMP + "\\new.fcs", mtime=5)
    zen_disk.write_file(ZEISS_TEMP + "\\new_R1.raw", mtime=5)
    zen_disk.write_file(ZEISS_TEMP + "\\new_R2.raw", mtime=6)
    zen_disk.write_file(ZEISS_TEMP + "\\notes.txt", mtime=9)

    paths = pm.get_latest_fcs_and_raws()

    names = [p.rsplit("\\", 1)[1] for p in paths]
    assert names[0] == "new.fcs"
    assert sorted(names[1:]) == ["new_R1.raw", "new_R2.raw"]


def test_latest_fcs_empty_folder_returns_empty(pm, zen_disk):
    zen_disk.make_dirs(ZEISS_TEMP)

    assert pm.get_latest_fcs_and_raws() == []
