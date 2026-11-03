"""
The overview analysis on a real image: tests/fixtures/guv_overview.czi with the preset "Cellpose"
from processing_config.json, the preset the automation ran on this very image on 2026-08-26.

That run, on the microscope PC (GPU), found two GUVs. Here, on the CPU with the versions pinned in
requirements.txt, the analysis is deterministic and finds two objects as well, but only one of them
is the same GUV: the other one the microscope found is not detected, and a smaller object 43 um
away is found instead. The analysis code and the preset have not changed since that run, so the
difference comes from the environment (GPU versus CPU, or other cellpose/torch versions on the
microscope PC). Open question, not a known bug - which is why it is not an xfail:

- test_finds_the_guv_the_microscope_found   the object both runs agree on, the real reference
- test_cpu_result_current_behaviour         what this environment gives today, frozen

Needs cellpose 3.0, torch and skimage (requirements.txt); skipped without them. Cellpose downloads
its model on the first run, into ~/.cellpose/models.
"""
import json
import math
import os
import subprocess
import sys

import pytest

cellpose = pytest.importorskip("cellpose")
pytest.importorskip("skimage")
pytest.importorskip("torch")

from importlib.metadata import version  # noqa: E402

pytestmark = pytest.mark.slow

if version("cellpose") != "3.0":
    pytest.skip("the expected values were made with cellpose 3.0 (requirements.txt), this is {}".format(
        version("cellpose")), allow_module_level=True)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CZI = os.path.join(ROOT, "tests", "fixtures", "guv_overview.czi")
PROCESSING_CONFIG = os.path.join(ROOT, "ZeissAPI", "config", "processing_config.json")

STAGE_Z = 2085.667

# temp/50e8c1ba-..._measurements_points.json of the run on the microscope, 2026-08-26
MICROSCOPE_RUN = [
    {"position": (41597.744648122156, 39234.160959621855), "radius": 8.870407243822914},
    {"position": (41579.56114207714, 39298.8521618575), "radius": 9.828866655687044},
]

# this environment, CPU, requirements.txt versions
CPU_RUN = [
    {"position": (41556.0098, 39244.3678), "radius": 5.2060},
    {"position": (41579.4859, 39299.8099), "radius": 8.6584},
]


@pytest.fixture(scope="module")
def processor():
    from data_processing.processor.zeiss_image_processor import ZeissImageProcessor

    with open(PROCESSING_CONFIG) as f:
        preset = json.load(f)["Cellpose"]

    return ZeissImageProcessor(CZI, **preset)


def nearest(points, xy):
    return min(points, key=lambda p: math.dist(p["position"][:2], xy))


def test_finds_the_guv_the_microscope_found(processor):
    reference = MICROSCOPE_RUN[1]
    found = nearest(processor.measurement_points, reference["position"])

    # 1 um is about 2.4 px at 0.414 um/px
    assert math.dist(found["position"][:2], reference["position"]) < 1.5
    assert found["radius"] == pytest.approx(reference["radius"], abs=1.5)


def test_cpu_result_current_behaviour(processor):
    # CURRENT BEHAVIOUR on this environment, frozen; see the module docstring for why it differs
    # from the run on the microscope. Changes when cellpose, torch or the analysis change.
    points = sorted(processor.measurement_points, key=lambda p: p["position"][0])

    assert len(points) == len(CPU_RUN)
    for point, expected in zip(points, CPU_RUN):
        assert point["position"][:2] == pytest.approx(expected["position"], abs=0.05)
        assert point["radius"] == pytest.approx(expected["radius"], abs=0.05)


def test_points_are_in_stage_um_at_the_image_z(processor):
    for point in processor.measurement_points:
        x, y, z = point["position"]
        # inside the 212 x 212 um field of view around the stage position of the image
        assert abs(x - 41582.224) < 106.1 and abs(y - 39297.208) < 106.1
        assert z == STAGE_Z


def test_every_point_has_an_id_and_is_selected(processor):
    # no object selection in this preset, so every object counts
    ids = [p["id"] for p in processor.measurement_points]

    assert len(set(ids)) == len(ids)
    assert all(p["selected"] is True for p in processor.measurement_points)


def test_main_processor_end_to_end(tmp_path):
    # The command line PythonAnalysisRunner builds, run as a real process from the project root
    saving_path = tmp_path / "A1_x_measurements_points.json"
    env = dict(os.environ, PYTHONPATH=ROOT, MPLBACKEND="Agg")

    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "data_processing", "main_processor.py"),
         "--type=overview", "--file_path={}".format(CZI), "--saving_path={}".format(saving_path),
         "--analysis_arguments=Cellpose", "--is_FCS=False", "--processing_config={}".format(PROCESSING_CONFIG)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)

    assert result.returncode == 0, result.stderr[-2000:]
    with open(saving_path) as f:
        data = json.load(f)

    # the JSON shape of CLAUDE.md: { "<uuid>": { "position": [x, y, z], "selected": true, ... } }
    assert len(data) == len(CPU_RUN)
    for key, entry in data.items():
        assert len(key) == 36
        assert len(entry["position"]) == 3
        assert entry["selected"] is True
        assert entry["source"] == CZI
    assert saving_path.with_suffix(".png").is_file()
