import pytest

from hopscotchdict import HopscotchDict


@pytest.mark.parametrize("log_array_size", [4, 8, 16],
	ids = ["small-array", "medium-array", "large-array"])
def test_make_indices(log_array_size):
	if log_array_size <= 7:
		expected_bit_length = 8
	elif log_array_size <= 15:
		expected_bit_length = 16
	elif log_array_size <= 31:
		expected_bit_length = 32
	elif log_array_size <= 63:
		expected_bit_length = 64

	indices = HopscotchDict._make_indices(2 ** log_array_size)

	assert len(indices) == 2 ** log_array_size
	assert indices.itemsize == expected_bit_length / 8
	assert indices[0] == -1


@pytest.mark.parametrize("nbhd_size", [8, 16, 32, 64],
	ids = ["8-neighbor", "16-neighbor", "32-neighbor", "64-neighbor"])
def test_make_nbhds(nbhd_size):
	nbhds = HopscotchDict._make_nbhds(nbhd_size, 32)

	assert len(nbhds) == 32
	assert nbhds.itemsize == nbhd_size / 8

	with pytest.raises(OverflowError):
		nbhds[0] = 2 ** nbhd_size

	nbhds[0] = 2 ** nbhd_size - 1


def test_clear_neighbor():
	hd = HopscotchDict()
	hd["test_clear_neighbor"] = True
	idx = hd._lookup("test_clear_neighbor")

	assert hd._nbhds[idx] != 0
	hd._clear_neighbor(idx, 0)
	assert hd._nbhds[idx] == 0


@pytest.mark.parametrize("creation_args", ["none", "list", "dict"],
	ids = ["no-creation-args", "creation-list", "creation-dict"])
def test_dict_creation(creation_args):
	keys = ("test_key_1", "test_key_2", "test_key_3", "test_key_4", "test_key_5")
	vals = (1, 2, 3, 4, 5)

	if creation_args == "none":
		hd = HopscotchDict()
	if creation_args == "list":
		hd = HopscotchDict(zip(keys, vals))
	if creation_args == "dict":
		hd = HopscotchDict(dict(zip(keys, vals)))

	assert hd._size == 8

	if creation_args == "none":
		assert len(hd) == 0
	else:
		assert len(hd) == 5
