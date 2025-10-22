import numpy as np
import os
from datetime import datetime


def read_uint32(f, count=1):
    """Reads `count` uint32 values from a binary file object."""
    return np.fromfile(f, dtype=np.uint32, count=count)


def read_confo_cor3(filepath: str) -> dict:
    """
    Reads Zeiss ConfoCor3 .raw photon arrival time files.

    Args:
        filepath (str): path to the .raw file

    Returns:
        dict: photon_data compatible with MATLAB photonData struct
    """
    photon_data = {
        "ph_sync": None,
        "ph_dtime": None,
        "ph_channel": None,
        "mark_sync": None,
        "mark_chan": None,
        "mark_dtime": None,
        "TTResult_SyncRate": None,
        "MeasDesc_Resolution": 1,
        "File_CreatingTime": datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat(),
        "HWSync_Divider": None,
        "MeasDesc_AcquisitionTime": None,
        "Headers": {}
    }

    with open(filepath, "rb") as f:
        # === HEADER ===
        header_text = f.read(64).decode("ascii", errors="ignore")
        photon_data["Headers"]["Header"] = header_text
        photon_data["Headers"]["Identifier"] = read_uint32(f, 4)
        settings = read_uint32(f, 4)
        photon_data["Headers"]["Settings"] = settings

        _ = read_uint32(f, 8)  # skip 8 uint32

        photon_data["TTResult_SyncRate"] = int(settings[3])

        # === DATA SECTION ===
        raw_records = read_uint32(f)

    # Photon arrival times in sync units (cumulative sum)
    ph_sync = np.cumsum(raw_records, dtype=np.uint64)

    # Channel ID (last character of header interpreted as a number)
    channel_number = int(header_text.strip()[-1:]) if header_text.strip()[-1:].isdigit() else 0
    ph_channel = np.ones_like(ph_sync) * channel_number
    ph_dtime = np.ones_like(ph_sync)

    meas_time_ms = ph_sync[-1] / photon_data["TTResult_SyncRate"]

    photon_data.update({
        "ph_sync": ph_sync,
        "ph_dtime": ph_dtime,
        "ph_channel": ph_channel,
        "MeasDesc_AcquisitionTime": meas_time_ms,
    })

    return photon_data
