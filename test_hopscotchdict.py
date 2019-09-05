import pytest

from hopscotchdict import HopscotchDict

from copy import copy
from random import randint, sample
from sys import version_info

from hypothesis import example, given, settings
from hypothesis.strategies import booleans, complex_numbers, deferred, dictionaries, floats, frozensets, lists, integers, none, one_of, text, tuples


oldpython = pytest.mark.skipif(version_info.major > 2, reason="Requires Python 2.7 to test")

dict_keys = deferred(lambda: one_of(none(), booleans(), integers(), floats(allow_infinity=False, allow_nan=False), complex_numbers(allow_infinity=False, allow_nan=False), text(), tuples(dict_keys), frozensets(dict_keys)))

dict_values = deferred(lambda: one_of(dict_keys, lists(dict_keys), dictionaries(dict_keys, dict_values)))

sample_dict = dictionaries(dict_keys, dict_values)


@settings(deadline=1000)
@given(integers(min_value=8, max_value=2**20))
def test_make_indices(array_size):
	if array_size <= 2**7:
		expected_bit_length = 8
	elif array_size <= 2**15:
		expected_bit_length = 16
	elif array_size <= 2**31:
		expected_bit_length = 32
	elif array_size <= 2**63:
		expected_bit_length = 64

	indices = HopscotchDict._make_indices(array_size)

	assert len(indices) == array_size
	assert indices.itemsize == expected_bit_length / 8
	assert all(map(lambda i: i == -1, indices))


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


@pytest.mark.parametrize("scenario", ["unnecessary", "near", "far", "displaced"],
	ids = ["unnecessary-action", "inside-neighborhood", "outside-neighborhood", "displaced-entry"])
def test_valid_free_up(scenario):
	hd = HopscotchDict()

	if scenario == "unnecessary":
		for i in range(2,7):
			hd[i] = "test_valid_free_up_{}".format(i)

		hd._free_up(0)

		assert hd._indices[0] == hd.FREE_ENTRY
		assert not hd._nbhds[0]

	elif scenario == "near":
		for i in range(1, 6):
			hd[i] = "test_valid_free_up_{}".format(i)

		# Move to index 6
		hd._free_up(1)

		# Make sure index 1 is open
		assert hd._indices[1] == hd.FREE_ENTRY
		assert not hd._nbhds[1] & 1 << 7

		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[1] & 1 << 2

		# Index 6 in _indices should point to index 0 in _keys, _values, _hashes
		assert hd._indices[6] == 0
		assert not hd._nbhds[6]

	elif scenario == "far":
		for i in range(1, 11):
			hd[i] = "test_valid_free_up_{}".format(i)

		# Move to index 4, 4 moves to 11
		hd._free_up(1)

		# Make sure index 1 is open
		assert hd._indices[1] == hd.FREE_ENTRY
		assert not hd._nbhds[1] & 1 << 7

		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[1] & 1 << 4

		# Index 4 in _indices should point to index 0 in other lists
		assert hd._indices[4] == 0
		assert not hd._nbhds[4] & 1 << 7

		# Make sure neighborhood knows where displaced entry is
		assert hd._nbhds[4] & 1

		# Index 11 in _indices should point to index 3 in other lists
		assert hd._indices[11] == 3
		assert not hd._nbhds[11]

	elif scenario == "displaced":
		hd._resize(16)

		hd[0] = "test_valid_free_up_0"
		hd[16] = "test_valid_free_up_16"

		for i in range(2,8):
			hd[i] = "test_valid_free_up_{}".format(i)

		# Move to index 2; 2 goes to 8
		hd._free_up(1)

		# Make sure index 1 is open
		assert hd._indices[1] == hd.FREE_ENTRY
		assert not hd._nbhds[1]

		# Index 2 in _indices should point to index 0 in other lists
		assert hd._indices[2] == 0
		assert not hd._nbhds[2] & 1 << 7

		# Index 8 in _indices should point to index 2 in other lists
		assert hd._indices[8] == 2
		assert not hd._nbhds[8]

		# Make sure neighborhoods knows where displaced entries are
		assert hd._nbhds[0] & 1 << 7
		assert hd._nbhds[0] & 1 << 5
		assert hd._nbhds[2] & 1 << 1


@pytest.mark.parametrize("scenario", ["no_space", "last_none", "last_distant"],
	ids = ["no_space", "last-index-no-neighbors", "last-index-distant-neighbors"])
def test_invalid_free_up(scenario):
	hd = HopscotchDict()

	if scenario == "no_space":
		for i in range(2, 8):
			hd[i] = "test_invalid_free_up_{}".format(i)

		with pytest.raises(RuntimeError):
			hd._free_up(2)

	elif scenario == "last_none":
		for i in range(1, 257, 32):
			hd[i] = "test_invalid_free_up_{}".format(i)

		with pytest.raises(RuntimeError):
			hd._free_up(1)

	elif scenario == "last_distant":
		hd._resize(32)

		hd[8] = "test_invalid_free_up_8"
		hd[9] = "test_invalid_free_up_9"
		hd[40] = "test_invalid_free_up_40"

		del hd[40]
		del hd[9]

		for i in range(1, 257, 32):
			hd[i] = "test_invalid_free_up_{}".format(i)

		with pytest.raises(RuntimeError):
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
		for i in range(6):
			hd[i] = "test_get_displaced_neighbors_{}".format(i)

		for i in range(6):
			assert hd._get_displaced_neighbors(i) == [i]


@given(dict_keys)
def test_lookup(key):
	hd = HopscotchDict()

	idx = abs(hash(key)) % hd._size
	hd[key] = True
	assert hd._lookup(key) == idx


@pytest.mark.parametrize("scenario", ["missing", "displaced", "outside", "free"],
	ids = ["missing-key", "displaced-key", "neighbor-outside-array", "neighbor-previously-freed"])
def test_lookup_fails(scenario):
	hd = HopscotchDict()

	if scenario == "missing":
		assert hd._lookup("test_lookup") == None

	elif scenario == "displaced":
		hd[3] = True
		hd[11] = True
		assert hd._lookup(3) == 4

	elif scenario == "outside":
		hd[7] = "test_lookup_7"
		hd._set_neighbor(7, 1)

		with pytest.raises(IndexError):
			hd._lookup(7)

	elif scenario == "free":
		hd[4] = "test_lookup"
		hd._indices[4] = hd.FREE_ENTRY

		with pytest.raises(RuntimeError):
			hd._lookup(4)


@pytest.mark.parametrize("scenario",
	["bad_size", "too_large", "nbhd_inc", "rsz_col"],
	ids = ["bad-length", "oversized-length",
		   "neighborhood-increase", "resize-collision"])
def test_resize(scenario):
	hd = HopscotchDict()

	if scenario == "bad_size":
		with pytest.raises(ValueError):
			hd._resize(25)

	elif scenario == "too_large":
		with pytest.raises(ValueError):
			hd._resize(2 ** 65)

	elif scenario == "nbhd_inc":
		for i in range(32):
			hd["test_resize_{}".format(i)] = i

		hd._resize(512)

		assert hd._nbhd_size == 16

		for i in range(32):
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

		for i in range(8):
			hd._set_neighbor(idx, i)

		assert hd._nbhds[idx] == 255


def test_clear():
	hd = HopscotchDict()

	for i in range(256):
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


def test_bare_init():
	hd = HopscotchDict()
	assert len(hd) == 0


@given(sample_dict)
def test_list_init(gen_dict):
	items = list(gen_dict.items())
	size = len(gen_dict)
	hd = HopscotchDict(items)
	assert len(hd) == size


@given(sample_dict)
def test_dict_init(gen_dict):
	hd = HopscotchDict(gen_dict)
	assert len(hd) == len(gen_dict)


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


@given(sample_dict)
def test_setitem_happy_path(gen_dict):
	hd = HopscotchDict()

	for (k, v) in gen_dict.items():
		hd[k] = v

	assert len(hd) == len(gen_dict)

	for key in gen_dict:
		assert hd[key] == gen_dict[key]
		assert hd._lookup(key) in hd._get_displaced_neighbors(abs(hash(key)) % hd._size)


@pytest.mark.parametrize("scenario",
	["overwrite", "density_resize", "snr", "bnr", "ovw_err", "ins_err"],
	ids = ["overwrite", "density-resize", "small-nbhd-resize",
		   "big-nbhd-resize", "overwrite-error", "insert-error"])
def test_setitem_special_cases(scenario):
	hd = HopscotchDict()

	if scenario == "overwrite":
		hd["test_setitem"] = False
		hd["test_setitem"] = True
		assert len(hd) == 1
		assert hd["test_setitem"]

	elif scenario == "density_resize":
		hd._resize(2 ** 16)

		for i in range(55000):
			hd[i] = i

		assert hd._size == 2 ** 17
		assert len(hd) == 55000
		for i in range(55000):
			assert hd[i] == i

	elif scenario == "ovw_err" or scenario == "ins_err":
		if scenario == "ovw_err":
			hd["test_setitem"] = False
		hd["test"] = True
		hd._values.pop()

		with pytest.raises(RuntimeError):
			hd["test_setitem"] = True

	elif scenario == "snr":
		for i in range(10, 17):
			hd[i] = "test_setitem_{}".format(i)

		assert hd._size == 32

		for i in range(1, 257, 32):
			hd[i] = "test_setitem_{}".format(i)

		hd[257] = "test_setitem_257"

		assert len(hd) == 16
		assert hd._size == 128

		for i in hd._keys:
			assert hd[i] == "test_setitem_{}".format(i)

	elif scenario == "bnr":
		for i in range(26250):
			hd[i] = "test_setitem_{}".format(i)

		assert hd._size == 2 ** 17

		for i in range(30001, 30001 + 32 * 2 ** 17, 2 ** 17):
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

	if scenario == "found":
		for i in range(1, 7):
			hd[i] = "test_delitem_{}".format(i)

		for key in hd._keys:
			assert hd._indices[hd._lookup(key)] == key - 1

		del hd[6]

		for key in hd._keys:
			assert hd._indices[hd._lookup(key)] == key - 1

		del hd[2]

		assert hd._indices[hd._lookup(1)] == 0
		assert hd._indices[hd._lookup(3)] == 2
		assert hd._indices[hd._lookup(4)] == 3
		assert hd._indices[hd._lookup(5)] == 1

		del hd[3]

		assert hd._indices[hd._lookup(1)] == 0
		assert hd._indices[hd._lookup(4)] == 2
		assert hd._indices[hd._lookup(5)] == 1

		for key in copy(hd._keys):
			del hd[key]

		assert len(hd) == 0
		assert max(hd._indices) == hd.FREE_ENTRY

	elif scenario == "missing":
		with pytest.raises(KeyError):
			del hd["test_delitem"]


@given(sample_dict)
def test_contains_and_has_key(gen_dict):
	hd = HopscotchDict(gen_dict)

	for key in hd._keys:
		assert key in hd

	assert "test_contains" not in hd
	assert not hd.has_key("test_contains")


@given(sample_dict)
def test_iter_and_len(gen_dict):
	hd = HopscotchDict(gen_dict)

	count = 0

	for key in hd:
		count += 1

	assert count == len(hd) == len(gen_dict)


@given(sample_dict)
def test_repr(gen_dict):
	hd = HopscotchDict(gen_dict)

	assert eval(repr(hd)) == hd


@pytest.mark.parametrize("scenario",
	["eq", "bad_type", "bad_len", "bad_keys", "bad_vals"],
	ids = ["equal", "type-mismatch", "length-mismatch",
		   "key-mismatch", "value-mismatch"])
def test_eq_and_neq(scenario):
	hd = HopscotchDict()
	dc = {}

	for i in range(5):
		hd["test_eq_and_neq_{}".format(i)] = i
		dc[u"test_eq_and_neq_{}".format(i)] = i

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


@given(sample_dict)
def test_keys(gen_dict):
	hd = HopscotchDict(gen_dict)

	keys = hd.keys()
	if version_info.major < 3:
		assert isinstance(keys, list)
	else:
		keys = list(keys)

	for key in gen_dict:
		assert key in keys


@given(sample_dict)
def test_values(gen_dict):
	hd = HopscotchDict(gen_dict)

	vals = hd.values()
	if version_info.major < 3:
		assert isinstance(vals, list)
	else:
		vals = list(vals)

	for key in gen_dict:
		assert gen_dict[key] in vals


@given(sample_dict)
def test_items(gen_dict):
	hd = HopscotchDict(gen_dict)

	items = hd.items()
	if version_info.major < 3:
		assert isinstance(items, list)
	else:
		items = list(items)

	for item_tuple in gen_dict.items():
		assert item_tuple in items


@oldpython
@given(sample_dict)
def test_iterkeys(gen_dict):
	hd = HopscotchDict(gen_dict)

	keys = hd.keys()

	for k in hd.iterkeys():
		assert k in keys


@oldpython
@given(sample_dict)
def test_itervalues(gen_dict):
	hd = HopscotchDict(gen_dict)

	vals = hd.values()

	for v in hd.itervalues():
		assert v in vals


@oldpython
@given(sample_dict)
def test_iteritems(gen_dict):
	hd = HopscotchDict(gen_dict)

	items = hd.items()

	for (k, v) in hd.iteritems():
		assert (k, v) in items


@given(sample_dict)
def test_reversed(gen_dict):
	hd = HopscotchDict(gen_dict)

	keys = hd.keys()
	if not isinstance(keys, list):
		keys = list(keys)

	rev_keys = list(reversed(hd))

	assert len(keys) == len(rev_keys)
	for i in range(len(keys)):
		assert keys[i] == rev_keys[len(keys) - i - 1]

@pytest.mark.parametrize("valid_key", [True, False],
	ids = ["stored-value", "default-value"])
def test_get(valid_key):
	hd = HopscotchDict()
	val = None

	if valid_key:
		hd["test_get"] = val = 1337
	else:
		val = 1017

	assert hd.get("test_get", 1017) == val


@pytest.mark.parametrize("scenario", ["valid_key", "invalid_key", "default"],
	ids = ["valid-key", "invalid-key", "default-value"])
def test_pop(scenario):
	hd = HopscotchDict()
	val = None

	if scenario == "valid_key":
		hd["test_pop"] = val = 1337
	else:
		val = 0

	if scenario != "invalid_key":
		assert hd.pop("test_pop", 0) == val
	else:
		with pytest.raises(KeyError):
			hd.pop("test_pop")


@given(sample_dict)
@example({})
def test_popitem(gen_dict):
	hd = HopscotchDict()

	if not gen_dict:
		with pytest.raises(KeyError):
			hd.popitem()
	else:
		hd.update(gen_dict)

		key = hd._keys[-1]
		val = hd._values[-1]

		cur_len = len(hd)
		assert (key, val) == hd.popitem()
		assert len(hd) == cur_len - 1
		assert key not in hd


@pytest.mark.parametrize("existing_key", [True, False],
	ids = ["no-use-default", "use-default"])
def test_setdefault(existing_key):
	hd = HopscotchDict()
	val = None

	if existing_key:
		hd["test_setdefault"] = val = 1337
	else:
		val = 1017

	assert hd.setdefault("test_setdefault", 1017) == val


@given(sample_dict)
def test_copy(gen_dict):
	hd = HopscotchDict(gen_dict)

	hdc = hd.copy()

	for key in hd._keys:
		assert id(hd[key]) == id(hdc[key])


@given(sample_dict)
def test_str(gen_dict):
	hd = HopscotchDict(gen_dict)

	assert str(hd) == str(gen_dict)
