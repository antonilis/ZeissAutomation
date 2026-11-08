import numpy as np
import copy
import re


def z_no_transform(px, stage_pos, scaling, tiles):
    """
    Return Z position without applying any transformation.
    :return: float, stage Z position in um
    """
    return stage_pos["z"]


def z_normal(px, stage_pos, scaling, tiles):
    """
    Return Z position adjusted by pixel Z offset and scaling.
    :return: float, stage Z position in um
    """
    if len(px) < 3:
        return stage_pos["z"]
    return stage_pos["z"] + px[2] * scaling["Z"] * 1e6





class PixelStageConverter:
    """
    Convert pixel coordinates to stage coordinates in X, Y, and Z.

    Uses image metadata for scaling and optional tile/Z-scan information.
    """
    def __init__(self, metadata, image_shape):
        self.metadata = metadata
        self.image_shape = self._normalize_image_shape(image_shape)
        self.tiles_lookup = self._build_tiles_lookup()


    def _normalize_image_shape(self, shape):
        """
        Normalize image shape to (H, W) for image with z dimension.
        :return: tuple (H, W)
        """
        if len(shape) == 2:
            return shape
        elif len(shape) == 3:
            _, h, w = shape
            return (h, w)
        else:
            raise ValueError(f"Unexpected image shape: {shape}")

    # -----------------------------
    # tile index → z lookup
    # -----------------------------
    def _build_tiles_lookup(self):
        """
        Build lookup dictionary from tile index to focus Z position.
        :return: dict {tile_index: z_position_in_stage_units}
        """
        lookup = {}
        tiles = self.metadata.get("tiles", [])

        for tile in tiles:
            matches = re.findall(r"\d+", tile.get("name", ""))
            if matches:
                idx = int(matches[-1]) - 1
                lookup[idx] = tile["z"]

        return lookup


    def convert_xy(self, px, mode="normal"):
        """
        Convert pixel X,Y to stage coordinates using scaling and image center.
        :return: tuple (x_stage, y_stage) in um
        """
        stage = self.metadata["stage_position"]
        scaling = self.metadata["scaling_um_per_pixel"]
        H, W = self.image_shape

        if mode == "normal":
            x = stage["x"] + (px[0] - H / 2 + 0.5) * scaling["X"] * 1e6
            y = stage["y"] + (px[1] - W / 2 + 0.5) * scaling["Y"] * 1e6
            return x, y

        if mode == "center":
            return stage["x"], stage["y"]

        raise ValueError("XY mode must be 'normal' or 'center'.")

    def convert_z_auto(self, px):
        """
        Automatically choosing the strategy based on metadata to convert pixel Z to stage Z based on Z-scan or tiles.
        :return: float, stage Z position in um
        """
        stage = self.metadata["stage_position"]
        scaling = self.metadata["scaling_um_per_pixel"]

        # 1. If z-scan
        z_scan = self.metadata.get("z_scan")
        if z_scan and "is_center_mode" in z_scan and z_scan['is_activated']:
            if len(px) >= 3:
                return stage["z"] + px[2] * scaling["Z"] * 1e6
            else:
                return stage["z"]

        # 2. Using tiles if there is no z-scan
        if len(px) >= 3:
            idx = int(px[2])
            return self.tiles_lookup.get(idx, stage["z"])

        # fallback
        return stage["z"]


    def convert_z(self, px, z_strategy):
        """
        Convert pixel Z using a provided strategy function.
        :return: float, stage Z position in um
        """
        stage = self.metadata["stage_position"]
        scaling = self.metadata["scaling_um_per_pixel"]
        return z_strategy(px, stage, scaling, self.tiles_lookup)


    def convert_points(self, points, xy_mode="normal", z_strategy=None):
        """
        Main method, a converter of a list of points from pixel coordinates to stage coordinates.
        :return: list of dictionaries with positions in stage coordinates (um)
        """
        if z_strategy is None:
            raise ValueError("z_strategy must be provided.")

        result = copy.deepcopy(points)
        for p in result:
            px = np.array(p["position"], dtype=float)
            x, y = self.convert_xy(px, xy_mode)

            # if z_strategy is PixelStageConverter method
            if callable(z_strategy):
                try:
                    z = z_strategy(px)
                except TypeError:
                    z = z_strategy(px, self.metadata["stage_position"], self.metadata["scaling_um_per_pixel"],
                                   self.tiles_lookup)
            else:
                raise ValueError("z_strategy must be callable")

            p["position"] = [x, y, z]

        return result

