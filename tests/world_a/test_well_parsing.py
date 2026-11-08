"""
split_well and parse_well_list read the plate selection typed into the macro GUI.
"""
import pytest

from zen_lib.acquisition_grid import parse_well_list, split_well


###################### split_well #####################################################################


@pytest.mark.parametrize("label, expected", [("A1", ("A", 1)), ("H12", ("H", 12))])
def test_split_well_single_and_two_digit(label, expected):
    assert split_well(label) == expected


@pytest.mark.parametrize("label", ["1A", "A", "AA1", "A1B", ""])
def test_split_well_bad_label_raises(label):
    with pytest.raises(ValueError):
        split_well(label)


###################### parse_well_list ################################################################


def test_single_well():
    assert parse_well_list("C3") == [("C", 3)]


def test_range_is_row_major_rectangle():
    assert parse_well_list("A1-B3") == [("A", 1), ("A", 2), ("A", 3), ("B", 1), ("B", 2), ("B", 3)]


def test_reversed_range_equals_forward():
    assert parse_well_list("B3-A1") == parse_well_list("A1-B3")


def test_items_keep_written_order():
    assert parse_well_list("E5, A1") == [("E", 5), ("A", 1)]


def test_duplicates_dropped_first_occurrence_wins():
    assert parse_well_list("A2, A1-A3, A2") == [("A", 2), ("A", 1), ("A", 3)]


def test_lowercase_and_whitespace():
    assert parse_well_list(" a1 - b2 ") == parse_well_list("A1-B2")


def test_empty_items_ignored():
    assert parse_well_list("A1,,B2,") == [("A", 1), ("B", 2)]


@pytest.mark.parametrize("text", ["", " , ,"])
def test_no_wells_raises(text):
    with pytest.raises(ValueError, match="No wells"):
        parse_well_list(text)


def test_two_dashes_raises():
    with pytest.raises(ValueError, match="A1-B2-C3"):
        parse_well_list("A1-B2-C3")


def test_no_plate_bounds_check_current_behaviour():
    # CURRENT BEHAVIOUR, NOT A SPECIFICATION. The parser does not know the plate, so wells that
    # do not exist on a 96-well plate (row I, column 0, column 13) are accepted as they are.
    # Whether they should be rejected is an open question; if the parser learns the plate, this
    # test changes in a commit of its own.
    assert parse_well_list("A0, A13, I1") == [("A", 0), ("A", 13), ("I", 1)]
