import numpy as np
import os
from datetime import datetime


def read_confo_cor3(filepath):
    """
    Reads Zeiss ConfoCor3 .raw photon arrival time files.
    Returns dict compatible with photonData struct.
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
        "File_CreatingTime": None,
        "HWSync_Divider": None,
        "MeasDesc_AcquisitionTime": None,
        "Headers": {}
    }

    with open(filepath, "rb") as f:
        # === HEADER ===
        header_text = f.read(64).decode("ascii", errors="ignore")
        photon_data["Headers"]["Header"] = header_text

        identifier = np.fromfile(f, dtype=np.uint32, count=4)
        photon_data["Headers"]["Identifier"] = identifier

        settings = np.fromfile(f, dtype=np.uint32, count=4)
        photon_data["Headers"]["Settings"] = settings

        # skip 8 uint32
        _ = np.fromfile(f, dtype=np.uint32, count=8)

        # Sync rate is the 4th setting entry
        photon_data["TTResult_SyncRate"] = int(settings[3])

        # === DATA SECTION ===
        t3record = np.fromfile(f, dtype=np.uint32)

    # Photon arrival times in sync units (cumulative sum)
    ph_sync = np.cumsum(t3record, dtype=np.uint64)

    # channel ID = last character of header interpreted as a number
    try:
        channel_number = int(header_text.strip()[-1])
    except ValueError:
        channel_number = 0

    ph_channel = np.ones_like(ph_sync) * channel_number
    ph_dtime = np.ones_like(ph_sync)

    meas_time_ms = ph_sync[-1] / photon_data["TTResult_SyncRate"]

    # File timestamp
    mtime = os.path.getmtime(filepath)
    file_time = datetime.fromtimestamp(mtime).isoformat()

    # Fill in dictionary
    photon_data.update({
        "ph_sync": ph_sync,
        "ph_dtime": ph_dtime,
        "ph_channel": ph_channel,
        "MeasDesc_AcquisitionTime": meas_time_ms,
        "File_CreatingTime": file_time,
    })

    return photon_data
