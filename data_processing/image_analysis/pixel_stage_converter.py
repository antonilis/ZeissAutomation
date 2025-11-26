import numpy as np
import copy
import re


def z_no_transform(px, stage_pos, scaling, tiles):
    return stage_pos["z"]


def z_normal(px, stage_pos, scaling, tiles):
    if len(px) < 3:
        return stage_pos["z"]
    return stage_pos["z"] + px[2] * scaling["Z"] * 1e6





class PixelStageConverter:

    def __init__(self, metadata, image_shape):
        self.metadata = metadata
        self.image_shape = self._normalize_image_shape(image_shape)
        self.tiles_lookup = self._build_tiles_lookup()

    # -----------------------------
    # shape normalizer
    # -----------------------------
    def _normalize_image_shape(self, shape):
        # shape: (H, W) or (C, H, W)
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
        lookup = {}
        tiles = self.metadata.get("tiles", [])

        for tile in tiles:
            matches = re.findall(r"\d+", tile.get("name", ""))
            if matches:
                idx = int(matches[-1]) - 1
                lookup[idx] = tile["z"]

        return lookup

    # -----------------------------
    # XY conversion
    # -----------------------------
    def convert_xy(self, px, mode="normal"):
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
        stage = self.metadata["stage_position"]
        scaling = self.metadata["scaling_um_per_pixel"]

        # 1. Jeśli jest z_scan
        z_scan = self.metadata.get("z_scan")
        if z_scan and "is_center_mode" in z_scan and z_scan['is_activated']:
            if len(px) >= 3:
                return stage["z"] + px[2] * scaling["Z"] * 1e6
            else:
                return stage["z"]

        # 2. Jeśli nie ma z_scan → użyj tiles
        if len(px) >= 3:
            idx = int(px[2])
            return self.tiles_lookup.get(idx, stage["z"])

        # fallback
        return stage["z"]

    # -----------------------------
    # Z conversion
    # -----------------------------
    def convert_z(self, px, z_strategy):
        stage = self.metadata["stage_position"]
        scaling = self.metadata["scaling_um_per_pixel"]
        return z_strategy(px, stage, scaling, self.tiles_lookup)

    # -----------------------------
    # FULL conversion — POINTS AS ARGUMENT
    # -----------------------------
    def convert_points(self, points, xy_mode="normal", z_strategy=None):
        if z_strategy is None:
            raise ValueError("z_strategy must be provided.")

        result = copy.deepcopy(points)
        for p in result:
            px = np.array(p["position"], dtype=float)
            x, y = self.convert_xy(px, xy_mode)

            # jeśli z_strategy jest metodą instancyjną PixelStageConverter
            if callable(z_strategy):
                try:
                    z = z_strategy(px)
                except TypeError:
                    # jeśli funkcja z zewnątrz wymaga więcej argumentów
                    z = z_strategy(px, self.metadata["stage_position"], self.metadata["scaling_um_per_pixel"],
                                   self.tiles_lookup)
            else:
                raise ValueError("z_strategy must be callable")

            p["position"] = [x, y, z]

        return result

