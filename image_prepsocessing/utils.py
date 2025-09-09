from imageio import imwrite

def extract_metadata(czi) -> dict:
    root = czi.meta  # ElementTree.Element

    metadata = {}

    scaling = {}
    for dist in root.findall(".//{*}Distance"):
        axis = dist.attrib.get("Id")
        val = dist.find(".//{*}Value")
        if axis and val is not None:
            scaling[axis] = float(val.text)
    metadata["scaling_um_per_pixel"] = scaling

    # --- Objective info ---
    objective = root.find(".//{*}ObjectiveSettings")
    if objective is not None:
        obj_name = objective.findtext(".//{*}Objective")
        magnification = objective.findtext(".//{*}Magnification")
        metadata["objective"] = {
            "name": obj_name,
            "magnification": float(magnification) if magnification else None
        }

    # --- Channels ---
    channels = []
    for ch in root.findall(".//{*}Channel"):
        ch_id = ch.attrib.get("Id")
        ch_name = ch.findtext(".//{*}Name")
        em = ch.findtext(".//{*}EmissionWavelength")
        ex = ch.findtext(".//{*}ExcitationWavelength")
        channels.append({
            "id": ch_id,
            "name": ch_name,
            "emission_nm": float(em) if em else None,
            "excitation_nm": float(ex) if ex else None
        })
    metadata["channels"] = channels

    # --- Acquisition date ---
    acq_date = root.findtext(".//{*}AcquisitionDate")
    if acq_date:
        metadata["acquisition_date"] = acq_date

    return metadata

def read_pictures(czi_path: str, out_dir: str = "."):

    czi = acp.CziFile(czi_path)
    base_name = os.path.splitext(os.path.basename(czi_path))[0]

    img, shp = czi.read_image(B=0, V=0, T=0)
    c_index = czi.dims.find('C')  # indeks osi C w tablicy img
    num_channels = img.shape[c_index]

    for channel in range(num_channels):

        img_channel = img[0, 0, 0, channel, 0, Ellipsis]

        out_path = os.path.join(out_dir, f"{base_name}_ch{channel}.npy")
        np.save(out_path, img_channel)
        if img_channel.dtype != np.uint8:
            img_norm = ((img_channel - img_channel.min()) / (img_channel.ptp()) * 255).astype(np.uint8)
        else:
            img_norm = img_channel

        out_path_png = os.path.join(out_dir, f"{base_name}_ch{channel+1}.png")
        imwrite(out_path_png, img_norm)



# for file_path in directions:
#
#     read_pictures(file_path, './images_arr')



