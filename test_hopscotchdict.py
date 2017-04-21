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


@pytest.mark.parametrize("open_location", ["near", "far"],
	ids = ["inside-neighborhood", "outside-neighborhood"])
def test_valid_free_up(open_location):
	hd = HopscotchDict()

	if open_location == "near":
		end_index = 6
	elif open_location == "far":
		end_index = 11

	for i in xrange(1, end_index):
		hd[i] = "test_{}".format(i)

	# Freeing up inside neighborhood: move to index 6
	# Freeing up outside neighborhood: move to index 4, 4 moves to 11
	hd._free_up(1)

	# Make sure index 1 is open
	assert hd._indices[1] == hd.FREE_ENTRY
	assert not hd._nbhds[1] & 1 << 7

	if open_location == "near":
		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[1] & 1 << 2

		# Index 6 in _indices should point to index 0 in _keys, _values, _hashes
		assert hd._indices[6] == 0
		assert not hd._nbhds[6] & 1 << 7

	elif open_location == "far":
		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[1] & 1 << 4

		# Index 4 in _indices should point to index 0 in other lists
		assert hd._indices[4] == 0
		assert not hd._nbhds[4] & 1 << 7

		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[4] & 1

		# Index 11 in _indices should point to index 3 in other lists
		assert hd._indices[11] == 3
		assert not hd._nbhds[11] & 1 << 7
		assert not hd._nbhds[11] & 1


def test_invalid_free_up():
	hd = HopscotchDict()
	hd._resize(16)

	for i in xrange(1, 129, 16):
		hd[i] = "test_{}".format(i)

	assert hd._nbhds[1] == 255

	with pytest.raises(Exception):
		hd._free_up(1)


@pytest.mark.parametrize("with_collisions", [True, False],
	ids = ["with-collisions", "no-collisions"])
def test_get_displaced_neighbors(with_collisions):
	hd = HopscotchDict()

	if with_collisions:
		hd[1] = "test_1"
		hd[9] = "test_9"
		hd[17] = "test_17"
		hd[3] = "test_3"
		hd[6] = "test_6"
		hd[14] = "test_14"

		assert hd._size == 8

		assert sorted(hd._get_displaced_neighbors(1)) == [1, 2, 4]
		assert hd._get_displaced_neighbors(3) == [3]
		assert sorted(hd._get_displaced_neighbors(6)) == [6, 7]

	else:
		for i in xrange(6):
			hd[i] = "test_{}".format(i)

		for i in xrange(6):
			assert hd._get_displaced_neighbors(i) == [i]


@pytest.mark.parametrize("scenario", ["missing", "found", "error"],
	ids = ["missing-key", "found-key", "lookup-error"])
def test_lookup(scenario):
	hd = HopscotchDict()

	if scenario == "missing":
		assert hd._lookup("test") == None

	elif scenario == "found":
		idx = abs(hash("test")) % hd._size
		hd["test"] = True
		assert hd._lookup("test") == idx

	elif scenario == "error":
		idx = abs(hash("test")) % hd._size
		hd["test"] = True
		hd._set_neighbor(idx, (idx - 1) % hd._size)

		with pytest.raises(AssertionError):
			hd._lookup("test")


@pytest.mark.parametrize("scenario",
	["bad_size", "too_large", "nbhd_inc", "rsz_col"],
	ids = ["bad-length", "oversized-length",
		   "neighborhood-increase", "resize-collision"])
def test_resize(scenario):
	hd = HopscotchDict()

	if scenario == "bad_size":
		with pytest.raises(AssertionError):
			hd._resize(25)

	elif scenario == "too_large":
		hd._nbhd_size = 64
		hd._resize(8)
		with pytest.raises(AssertionError):
			hd._resize(2 ** 65)

	elif scenario == "nbhd_inc":
		for i in xrange(32):
			hd["test_{}".format(i)] = i

		hd._resize(512)

		assert hd._nbhd_size == 16

		for i in xrange(32):
			assert hd["test_{}".format(i)] == i

	elif scenario == "rsz_col":
		hd[1] = "test_1"
		hd[17] = "test_17"

		hd._resize(16)

		assert hd[1] == "test_1"
		assert hd[17] == "test_17"
