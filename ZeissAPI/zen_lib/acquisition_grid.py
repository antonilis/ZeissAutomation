import json

from System.IO import Path

from zen_lib.runtime_config import log


###################### extension methods, imported into THIS compilation unit #########################
# GetTileRegionInfos is a .NET extension method on ZenExperiment, not a member of it, and
# IronPython surfaces extension methods only in the compilation unit that imported their
# namespace. Every .py file is its own compilation unit, so these lines have to stand here as
# well as in zen_api.py - a shared helper would import them into the helper's scope, not this one.
# See docs/zen_api/extension-methods.md.

import clr

import Zeiss.Micro.LM.Scripting
clr.ImportExtensions(Zeiss.Micro.LM.Scripting)


###################### reading a plate selection ######################################################


def split_well(label):
    """
    Splits a well label into its letter and its number.
    :param str label: for example "A1" or "H12"
    :return: tuple (letter, number)
    """
    letter = label[:1]
    number = label[1:]

    if not letter.isalpha() or not number.isdigit():
        raise ValueError("Cannot read the well '{}', expected a letter followed by a number, like A1".format(label))

    return letter, int(number)


def parse_well_list(text):
    """
    Reads a plate selection such as "A1-A12, C3, E5-E8" into the wells it names.

    An item is either a single well or two wells joined by a dash, which selects the whole
    rectangle between them. "A1-C4" on its own therefore means exactly what the old start and
    end fields meant, so a selection that worked before still works and nothing has to be
    learned to keep things as they were. Several items are what the two fields could not
    express at all: "A1-H1, A4-H4" is two separate columns in one run.

    Wells keep the order they were written in and repeats are dropped, so overlapping items
    are harmless. A range written backwards is read the same as one written forwards.

    :param str text: contents of the wells text box
    :return: list of (letter, number) tuples
    """
    wells = []
    seen = set()

    for item in text.split(","):
        item = item.strip().upper()

        if not item:
            continue

        corners = [part.strip() for part in item.split("-")]

        # a single well is the rectangle between itself and itself
        if len(corners) == 1:
            corners = corners * 2

        if len(corners) != 2:
            raise ValueError("Cannot read the well range '{}', expected something like A1-C4".format(item))

        first_letter, first_number = split_well(corners[0])
        last_letter, last_number = split_well(corners[1])

        letters = range(min(ord(first_letter), ord(last_letter)),
                        max(ord(first_letter), ord(last_letter)) + 1)
        numbers = range(min(first_number, last_number), max(first_number, last_number) + 1)

        for letter in letters:
            for number in numbers:
                well = (chr(letter), number)

                if well not in seen:
                    seen.add(well)
                    wells.append(well)

    if not wells:
        raise ValueError("No wells were given. Write something like A1-C4, or A1-H1, A4-H4")

    return wells


###################### the grid of overview points ####################################################


class AcquisitionGrid:
    """
    Class for the fast generation of the points on which one will perform the full pipeline
    of automated processes

    param RuntimeConfig config: configuration built by the macro, used only for the directory
    in which points_for_overview.json has to be saved
    param ZenApi zeiss_api: the ZEN runtime built by the macro, used in experiment mode to read
    the tile regions off a saved experiment
    """

    def __init__(
            self,
            config,
            zeiss_api,

            # 'available modes are: experiment' or 'manual', experiment mode reads the points from the centers of the tiles, manual generates the points by
            # specifying the shifts in x, y and start/end position).
            mode="experiment",

            experiment_name="AI_sample_finder",  # works in experiment mode: name of the .czexp file to read points from
            manual_points=None,
            # dictionairy with the keys: "wells", "shift_x", "shift_y", "start_position". "wells" is
            # a selection in the convention of the plate, for example "A1-C4" for a rectangle or
            # "A1-H1, A4-H4, E5" for two whole columns and one extra well, while start_position is the
            # real stage position in um of the FIRST well of that selection. Every other well is placed
            # from it using the shifts.

            subgrid=None
            # dictionary with the keys "rows", "cols", "shift_x" and "shift_y". Every point produced
            # by the chosen mode is then replaced by a rows x cols grid centred on it, which is how
            # one gets several fields of view inside a single well. Omitted, or 1x1, means no sub-grid.
    ):
        self.config = config
        self.zeiss_api = zeiss_api
        self.experiment_name = experiment_name
        self.mode = mode
        self.manual_points = manual_points or []
        self.subgrid = subgrid or {}

        # required for savings points in the directory compatible with automation pipeline
        self.measuring_points_path = config.measurements

        # Choosing the method suitable mode of the points generation
        if self.mode == "experiment":
            self.points_for_overview = self.calculate_points_for_overview()
        elif self.mode == "manual":
            self.points_for_overview = self.generate_grid_from_args()
        else:
            raise ValueError("Unknown mode: {}".format(self.mode))

        # Applied to whatever the chosen mode produced, so that the arithmetic exists once and
        # both modes gain the sub-grid at the same time
        self.points_for_overview = self.expand_with_subgrid(self.points_for_overview)

    def calculate_points_for_overview(self):
        """
        Reads the centers of the tiles from the .czexp file name
        return:
        list[dict]: List of points with keys:
            - "name": grid label (e.g. "A1")
            - "position": [x, y, z] coordinates
        """
        exp = self.zeiss_api.get_experiment(self.experiment_name)
        tile_region_objects = exp.GetTileRegionInfos(0)

        points_for_overview = []
        for tile in tile_region_objects:
            points_for_overview.append({
                "position": [tile.CenterX, tile.CenterY, tile.Z],
                "name": tile.Name,
            })
        return points_for_overview

    def generate_grid_from_args(self):
        """
        Generates the 3D points of the wells named in the manual configuration. The selection is a
        list of plate labels and ranges (e.g. "A1-C4" or "A1-H1, A4-H4, E5"), the stage position in
        start_position is the position of the first well of that selection, and every other well is
        placed from the constant shifts in X and Y.

        return: list[dict]: List of points with keys:
                - "name": grid label (e.g. "A1")
                - "position": [x, y, z] coordinates
        """

        cfg = self.manual_points

        required = ["wells", "shift_x", "shift_y", "start_position"]
        for r in required:
            if r not in cfg:
                raise ValueError("Missing '{}' in manual_points".format(r))

        wells = parse_well_list(cfg["wells"])

        shift_x = cfg["shift_x"]
        shift_y = cfg["shift_y"]
        base_x, base_y, base_z = cfg["start_position"]

        # Every well is placed relative to the first one of the selection rather than to its own
        # position in the list, so the order the items were typed in cannot move the whole plate,
        # and a selection that does not start at the top left corner stays where it belongs
        anchor_letter, anchor_number = wells[0]

        points = []
        for letter, number in wells:
            x = base_x + (number - anchor_number) * shift_x
            y = base_y + (ord(letter) - ord(anchor_letter)) * shift_y
            z = base_z
            name = "{}{}".format(letter, number)
            points.append({
                "name": name,
                "position": [x, y, z]
            })
        log("Generated {} manual grid points.".format(len(points)))
        return points

    def expand_with_subgrid(self, points):
        """
        Replaces every point with a grid of points centred on it, which is how one gets several
        fields of view inside a single well.

        The original point stays the centre of its own sub-grid, so switching a sub-grid on does not
        move the wells that were already being visited. Names are the original name followed by the
        row and column, which keeps them unique - and they have to be unique, because the name is
        the only thing telling apart the overview image and the measurement file of two points in
        the same run.

        :param list points: points with the keys "name" and "position"
        :return: list of points, named "A1_r1c1", "A1_r1c2" and so on
        """
        if not self.subgrid:
            return points

        required = ["rows", "cols", "shift_x", "shift_y"]

        for key in required:
            if key not in self.subgrid:
                raise ValueError("Missing '{}' in subgrid".format(key))

        rows = int(self.subgrid["rows"])
        cols = int(self.subgrid["cols"])

        if rows < 1 or cols < 1:
            raise ValueError("Sub-grid needs at least one row and one column, got {}x{}".format(
                rows, cols))

        # 1x1 is how the GUI says 'no sub-grid', and it must not rename the points
        if rows == 1 and cols == 1:
            return points

        shift_x = self.subgrid["shift_x"]
        shift_y = self.subgrid["shift_y"]

        # Offsets around the centre: three columns give [-shift, 0, +shift], two give
        # [-shift/2, +shift/2], so the centre of the sub-grid is always the original point
        x_offsets = [(c_idx - (cols - 1) / 2.0) * shift_x for c_idx in range(cols)]
        y_offsets = [(r_idx - (rows - 1) / 2.0) * shift_y for r_idx in range(rows)]

        expanded = []

        for point in points:
            x, y, z = point["position"]

            for r_idx, y_offset in enumerate(y_offsets):
                for c_idx, x_offset in enumerate(x_offsets):
                    expanded.append({
                        "name": "{}_r{}c{}".format(point["name"], r_idx + 1, c_idx + 1),
                        "position": [x + x_offset, y + y_offset, z]
                    })

        log("Expanded {} points into {} with a {}x{} sub-grid".format(
            len(points), len(expanded), rows, cols))

        return expanded

    def save_overview_points(self):
        """
        Writes the generated points to points_for_overview.json, which is what main_macro reads.
        :return: None
        """
        file_name = "points_for_overview.json"
        saving_path = Path.Combine(self.measuring_points_path, file_name)
        with open(saving_path, "w") as file:
            json.dump(self.points_for_overview, file, indent=2)

        log("Saved {} overview points to {}".format(len(self.points_for_overview), saving_path))
