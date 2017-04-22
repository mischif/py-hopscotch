import pytest

from hopscotchdict import HopscotchDict

from random import randint, sample

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

@pytest.mark.parametrize("out_of_bounds_neighbor", [True, False],
	ids = ["outside-neighborhood", "inside-neighborhood"])
def test_clear_neighbor(out_of_bounds_neighbor):
	hd = HopscotchDict()
	hd["test_clear_neighbor"] = True
	idx = hd._lookup("test_clear_neighbor")

	if out_of_bounds_neighbor:
		with pytest.raises(ValueError):
			hd._clear_neighbor(idx, 8)
	else:
		assert hd._nbhds[idx] != 0
		hd._clear_neighbor(idx, 0)
		assert hd._nbhds[idx] == 0


@pytest.mark.parametrize("scenario", ["near", "far", "last_none", "last_distant"],
	ids = ["inside-neighborhood", "outside-neighborhood",
		   "last-index-no-neighbors", "last-index-distant-neighbors"])
def test_valid_free_up(scenario):
	hd = HopscotchDict()

	if scenario == "last_none" or scenario == "last_distant":
		assert False

	if scenario == "near":
		end_index = 6
	elif scenario == "far":
		end_index = 11

	for i in xrange(1, end_index):
		hd[i] = "test_valid_free_up_{}".format(i)

	# Freeing up inside neighborhood: move to index 6
	# Freeing up outside neighborhood: move to index 4, 4 moves to 11
	hd._free_up(1)

	# Make sure index 1 is open
	assert hd._indices[1] == hd.FREE_ENTRY
	assert not hd._nbhds[1] & 1 << 7

	if scenario == "near":
		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[1] & 1 << 2

		# Index 6 in _indices should point to index 0 in _keys, _values, _hashes
		assert hd._indices[6] == 0
		assert not hd._nbhds[6] & 1 << 7

	elif scenario == "far":
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

	for i in xrange(10, 17):
		hd[i] = "test_invalid_free_up_{}".format(i)

	for i in xrange(1, 257, 32):
		hd[i] = "test_invalid_free_up_{}".format(i)

	assert hd._nbhds[1] == 255

	with pytest.raises(Exception):
		hd._free_up(1)


@pytest.mark.parametrize("with_collisions", [True, False],
	ids = ["with-collisions", "no-collisions"])
def test_get_displaced_neighbors(with_collisions):
	hd = HopscotchDict()

	if with_collisions:
		hd[1] = "test_get_displaced_neighbors_1"
		hd[9] = "test_get_displaced_neighbors_9"
		hd[17] = "test_get_displaced_neighbors_17"
		hd[3] = "test_get_displaced_neighbors_3"
		hd[6] = "test_get_displaced_neighbors_6"
		hd[14] = "test_get_displaced_neighbors_14"

		assert hd._size == 8

		assert hd._get_displaced_neighbors(1) == [1, 2, 4]
		assert hd._get_displaced_neighbors(3) == [3]
		assert hd._get_displaced_neighbors(6) == [6, 7]

	else:
		for i in xrange(6):
			hd[i] = "test_get_displaced_neighbors_{}".format(i)

		for i in xrange(6):
			assert hd._get_displaced_neighbors(i) == [i]


@pytest.mark.parametrize("scenario", ["missing", "found", "displaced", "error"],
	ids = ["missing-key", "found-key", "displaced-key", "lookup-error"])
def test_lookup(scenario):
	hd = HopscotchDict()

	if scenario == "missing":
		assert hd._lookup("test_lookup") == None

	elif scenario == "found":
		idx = abs(hash("test_lookup")) % hd._size
		hd["test_lookup"] = True
		assert hd._lookup("test_lookup") == idx

	elif scenario == "displaced":
		idx = abs(hash("test_lookup_1")) % hd._size
		hd["test_lookup_1"] = True
		hd["test_lookup_9"] = True
		assert hd._lookup("test_lookup_1") == idx + 1

	elif scenario == "error":
		idx = abs(hash("test_lookup")) % hd._size
		hd["test_lookup"] = True
		hd._set_neighbor(idx, (idx - 1) % hd._size)
		hd._set_neighbor(idx, (idx + 1) % hd._size)

		with pytest.raises(AssertionError):
			hd._lookup("test_lookup")


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
		with pytest.raises(AssertionError):
			hd._resize(2 ** 65)

	elif scenario == "nbhd_inc":
		for i in xrange(32):
			hd["test_resize_{}".format(i)] = i

		hd._resize(512)

		assert hd._nbhd_size == 16

		for i in xrange(32):
			assert hd["test_resize_{}".format(i)] == i

	elif scenario == "rsz_col":
		hd[1] = "test_1"
		hd[17] = "test_17"

		hd._resize(16)

		assert hd[1] == "test_1"
		assert hd[17] == "test_17"


@pytest.mark.parametrize("out_of_bounds_neighbor", [True, False],
	ids = ["outside-neighborhood", "inside-neighborhood"])
def test_set_neighbor(out_of_bounds_neighbor):
	hd = HopscotchDict()
	hd["test_set_neighbor"] = True
	idx = hd._lookup("test_set_neighbor")

	if out_of_bounds_neighbor:
		with pytest.raises(ValueError):
			hd._set_neighbor(idx, 8)
	else:
		assert hd._nbhds[idx] != 255

		for i in xrange(8):
			hd._set_neighbor(idx, i)

		assert hd._nbhds[idx] == 255


def test_clear():
	hd = HopscotchDict()

	for i in xrange(256):
		hd["test_clear_{}".format(i)] = i

	hd.clear()

	assert hd._count == 0
	assert hd._size == 8
	assert hd._nbhd_size == 8

	assert not hd._keys
	assert not hd._values
	assert not hd._hashes

	assert len(hd._indices) == 8
	assert len(set(hd._indices)) == 1

	assert len(hd._nbhds) == 8
	assert len(set(hd._nbhds)) == 1


@pytest.mark.parametrize("creation_args", ["none", "list", "dict"],
	ids = ["no-creation-args", "creation-list", "creation-dict"])
def test_init(creation_args):
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


@pytest.mark.parametrize("valid_key", [True, False],
	ids = ["valid-key", "invalid-key"])
def test_getitem(valid_key):
	hd = HopscotchDict()

	if valid_key:
		hd["test_getitem"] = True
		assert hd["test_getitem"]
	else:
		with pytest.raises(KeyError):
			assert hd["test_getitem"]


@pytest.mark.parametrize("scenario",
	["insert", "overwrite", "density_resize", "snr", "bnr", "ovw_err", "ins_err",
	 "lkp_err"],
	ids = ["insert", "overwrite", "density-resize", "small-nbhd-resize",
		   "big-nbhd-resize", "overwrite-error", "insert-error", "lookup-error"])
def test_setitem(scenario):
	hd = HopscotchDict()

	if scenario == "insert":
		for i in sample(xrange(10000), 1000):
			hd["test_setitem_{}".format(i)] = i

		assert len(hd) == 1000
		for key in hd._keys:
			i = int(key.split("_")[-1])
			assert hd["test_setitem_{}".format(i)] == i

	elif scenario == "overwrite":
		hd["test_setitem"] = False
		hd["test_setitem"] = True
		assert len(hd) == 1
		assert hd["test_setitem"]

	elif scenario == "density_resize":
		import pdb
		for i in xrange(105000):
			hd["test_setitem_{}".format(i)] = i

		for i in xrange(105000):
			assert hd["test_setitem_{}".format(i)] == i

	elif scenario == "ovw_err" or scenario == "ins_err":
		if scenario == "ovw_err":
			hd["test_setitem"] = False
		hd["test"] = True
		hd._values.pop()

		with pytest.raises(AssertionError):
			hd["test_setitem"] = True

	elif scenario == "lkp_err":
		idx = abs(hash("test_setitem")) % hd._size
		hd["test_setitem"] = False
		hd._indices[idx] = hd.FREE_ENTRY

		with pytest.raises(AssertionError):
			hd["test_setitem"] = True

	elif scenario == "snr":
		for i in xrange(10, 17):
			hd[i] = "test_setitem_{}".format(i)

		assert hd._size == 32

		for i in xrange(1, 257, 32):
			hd[i] = "test_setitem_{}".format(i)

		hd[257] = "test_setitem_257"

		assert len(hd) == 16
		assert hd._size == 128

		for i in hd._keys:
			assert hd[i] == "test_setitem_{}".format(i)

	elif scenario == "bnr":
		for i in xrange(26250):
			hd[i] = "test_setitem_{}".format(i)

		assert hd._size == 2 ** 17

		for i in xrange(30001, 30001 + 32 * 2 ** 17, 2 ** 17):
			hd[i] = "test_setitem_{}".format(i)

		assert len(hd) == 26282

		hd[4224305] = "test_setitem_4224305"

		assert len(hd) == 26283
		assert hd._size == 2 ** 18

		for i in hd._keys:
			assert hd[i] == "test_setitem_{}".format(i)


@pytest.mark.parametrize("scenario", ["found", "missing"],
	ids = ["found-key", "missing-key"])
def test_delitem(scenario):
	hd = HopscotchDict()
	idx = abs(hash("test_delitem")) % hd._size

	if scenario == "found":
		hd["test_delitem"] = True
		assert len(hd) == 1

		del hd["test_delitem"]
		assert len(hd) == 0
		assert hd._indices[idx] == hd.FREE_ENTRY

	elif scenario == "missing":
		with pytest.raises(KeyError):
			del hd["test_delitem"]


@pytest.mark.parametrize("valid_key", [True, False],
	ids = ["valid-key", "invalid-key"])
def test_contains(valid_key):
	hd = HopscotchDict()

	if valid_key:
		hd["test_contains"] = True

	assert ("test_contains" in hd) == valid_key


def test_iter_and_len():
	hd = HopscotchDict()

	count = 0
	limit = randint(1, 10000)
	for i in sample(xrange(10000), limit):
		hd["test_iter_{}".format(i)] = i

	for key in hd:
		count += 1

	assert count == limit == len(hd)


def test_repr():
	for r in xrange(100):
		hd = HopscotchDict()

		for i in sample(xrange(10000), 100):
			hd["test_repr_{}".format(i)] = i

		for key in hd._keys:
			if key not in hd:
				import pdb
				pdb.set_trace()

		assert eval(repr(hd)) == hd


@pytest.mark.parametrize("scenario",
	["eq", "bad_type", "bad_len", "bad_keys", "bad_vals"],
	ids = ["equal", "type-mismatch", "length-mismatch",
		   "key-mismatch", "value-mismatch"])
def test_eq_and_neq(scenario):
	hd = HopscotchDict()
	dc = {}

	for i in xrange(5):
		hd["test_eq_and_neq_{}".format(i)] = i
		dc["test_eq_and_neq_{}".format(i)] = i

	if (scenario == "bad_len"
		or scenario == "bad_keys"):
			dc.pop("test_eq_and_neq_4")

	if scenario == "bad_keys":
		dc["test_eq_and_neq_5"] = 4

	if scenario == "bad_vals":
		dc["test_eq_and_neq_0"] = False

	if scenario == "bad_type":
		assert hd != dc.items()

	elif scenario != "eq":
		assert hd != dc

	else:
		assert hd == dc


def test_items_and_iteritems():
	hd = HopscotchDict()

	for i in sample(xrange(10000), 100):
		hd["test_items_and_iteritems_{}".format(i)] = i

	items = hd.items()
	for item in hd.iteritems():
		assert item in items


def test_keys_and_iterkeys():
	hd = HopscotchDict()

	for i in sample(xrange(10000), 100):
		hd["test_keys_and_iterkeys_{}".format(i)] = i

	keys = hd.keys()
	for key in hd.iterkeys():
		assert key in keys


def test_values_and_itervalues():
	hd = HopscotchDict()

	for i in sample(xrange(10000), 100):
		hd["test_values_and_itervalues_{}".format(i)] = i

	vals = hd.values()
	for val in hd.itervalues():
		assert val in vals


def test_reversed():
	hd = HopscotchDict()

	for i in sample(xrange(10000), 100):
		hd["test_reversed_{}".format(i)] = i

	keys = hd.keys()
	rev_keys = list(reversed(hd))

	assert len(keys) == len(rev_keys)
	for i in xrange(len(keys)):
		assert keys[i] == rev_keys[len(keys) - i - 1]
