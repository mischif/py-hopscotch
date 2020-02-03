# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from copy import copy
from struct import calcsize, unpack_from
from sys import version_info

import pytest

from hypothesis import example, given, seed, settings
from hypothesis.strategies import integers
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from py_hopscotch_dict import HopscotchDict
from test import dict_keys, dict_values, max_dict_entries, sample_dict


@given(sample_dict, integers())
def test_get_lookup_index_info(gen_dict, lookup_idx):
	hd = HopscotchDict(gen_dict)

	if lookup_idx < 0 or lookup_idx >= hd._size:
		with pytest.raises(ValueError):
			hd._get_lookup_index_info(lookup_idx)
	else:
		data_idx, neighbors = hd._get_lookup_index_info(lookup_idx)
		for idx in neighbors:
			data_idx, _ = hd._get_lookup_index_info(idx)
			assert abs(hash(hd._keys[data_idx])) % hd._size == lookup_idx


@given(sample_dict, integers(), integers(min_value=-1), integers(min_value=0))
def test_set_lookup_index_info(gen_dict, lookup_idx, data_idx, nbhd):
	hd = HopscotchDict(gen_dict)

	if lookup_idx < 0 or lookup_idx >= hd._size:
		with pytest.raises(ValueError):
			hd._set_lookup_index_info(lookup_idx, data=data_idx, nbhd=nbhd)
	else:
		nbhd = min(nbhd, 2 ** hd._nbhd_size - 1) 
		data_idx = min(nbhd, 2 ** (hd._nbhd_size - 1) - 1)
		hd._set_lookup_index_info(lookup_idx, data=data_idx, nbhd=nbhd)

		lookup_offset = calcsize(hd._pack_fmt) * lookup_idx
		retrieved_idx, retrieved_nbhd = unpack_from(hd._pack_fmt, hd._lookup_table, lookup_offset)

		assert (retrieved_idx, retrieved_nbhd) == (data_idx, nbhd)


@given(sample_dict, integers())
def test_get_open_neighbor(gen_dict, lookup_idx):
	hd = HopscotchDict(gen_dict)

	if lookup_idx < 0 or lookup_idx >= hd._size:
		with pytest.raises(ValueError):
			hd._get_open_neighbor(lookup_idx)
	else:
		open_idx = hd._get_open_neighbor(lookup_idx)
		for idx in range(lookup_idx, open_idx if open_idx is not None else lookup_idx + hd._nbhd_size):
			data_idx, _ = hd._get_lookup_index_info(idx)
			assert data_idx != hd.FREE_ENTRY


@given(integers(max_value=max_dict_entries))
def test_make_lookup_table(tbl_size):
	if tbl_size < 0:
		with pytest.raises(ValueError):
			HopscotchDict._make_lookup_table(tbl_size)
	else:
		tbl, fmt = HopscotchDict._make_lookup_table(tbl_size)

		if tbl_size.bit_length() < 8:
			assert fmt == "b B"
		elif tbl_size.bit_length() < 16:
			assert fmt == ">h H"
		elif tbl_size.bit_length() < 32:
			assert fmt == ">i I"
		else:
			assert fmt == ">l L"


def test_clear_neighbor():
	hd = HopscotchDict()
	hd["test_clear_neighbor"] = True

	with pytest.raises(ValueError):
		hd._clear_neighbor(-1, 0)

	with pytest.raises(ValueError):
		hd._clear_neighbor(0, -1)

	with pytest.raises(ValueError):
		hd._clear_neighbor(10, 0)

	with pytest.raises(ValueError):
		hd._clear_neighbor(0, 10)

	lookup_idx, _ = hd._lookup("test_clear_neighbor")
	assert len(hd._get_lookup_index_info(lookup_idx)[1]) > 0

	hd._clear_neighbor(lookup_idx, 0)
	assert len(hd._get_lookup_index_info(lookup_idx)[1]) == 0


@pytest.mark.parametrize("scenario", ["unnecessary", "far", "displaced"],
	ids = ["unnecessary-action", "outside-neighborhood", "displaced-entry"])
def test_valid_free_up(scenario):
	hd = HopscotchDict()

	if scenario == "unnecessary":
		with pytest.raises(ValueError):
			hd._free_up(-1)

		with pytest.raises(ValueError):
			hd._free_up(10)

		for i in range(2,7):
			hd[i] = "test_valid_free_up_{}".format(i)

		hd._free_up(0)

		# Nothing was stored at the index, so nothing to do
		data_idx, neighbors = hd._get_lookup_index_info(0)
		assert data_idx == hd.FREE_ENTRY
		assert len(neighbors) == 0

		hd._free_up(4)

		# The index has an open neighbor, so nothing to do
		data_idx, neighbors = hd._get_lookup_index_info(4)
		assert data_idx == 2
		assert neighbors == [4]

	elif scenario == "far":
		for i in range(1, 11):
			hd[i] = "test_valid_free_up_{}".format(i)

		# Entry at index 4 moves to 11
		hd._free_up(1)

		data_idx, neighbors = hd._get_lookup_index_info(1)

		# The entry at index 1 will not move as a neighbor will open up first
		assert data_idx == 0
		assert neighbors == [1]

		data_idx, neighbors = hd._get_lookup_index_info(4)

		# Index 4 in _lookup_table should be empty
		assert data_idx == hd.FREE_ENTRY
		assert neighbors == [11]

		data_idx, neighbors = hd._get_lookup_index_info(11)

		# Index 11 in _lookup_table should point to index 3 in other lists
		assert data_idx == 3
		assert len(neighbors) == 0

	elif scenario == "displaced":
		hd._resize(16)

		for i in range(14, 63, 16):
			hd[i] = "test_valid_free_up_{}".format(i)

		for i in range(2, 9):
			hd[i] = "test_valid_free_up_{}".format(i)

		del hd[30]

		assert hd._get_lookup_index_info(1) == (3, [])
		assert hd._get_lookup_index_info(15) == (hd.FREE_ENTRY, [])

		hd._free_up(1)

		assert hd._get_lookup_index_info(1) == (hd.FREE_ENTRY, [])
		assert hd._get_lookup_index_info(15) == (3, [])


@pytest.mark.parametrize("scenario", ["full_wraps", "full", "last_distant"],
	ids = ["full-neighborhood-wraps-array", "full-neighborhood", "last-index-distant-neighbors"])
def test_invalid_free_up(scenario):
	hd = HopscotchDict()

	if scenario == "full_wraps":
		hd._resize(16)
		for i in range(12, 125, 16):
			hd[i] = "test_invalid_free_up_{}".format(i)

		with pytest.raises(RuntimeError):
			hd._free_up(12)

	elif scenario == "full":
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
		hd[3] = "test_get_displaced_neighbors_3"
		hd[17] = "test_get_displaced_neighbors_17"
		hd[6] = "test_get_displaced_neighbors_6"
		hd[14] = "test_get_displaced_neighbors_14"

		assert hd._size == 8

		lookup_offset = calcsize(hd._pack_fmt) * 1
		_, nbhd = unpack_from(hd._pack_fmt, hd._lookup_table, lookup_offset)
		assert hd._get_displaced_neighbors(1, nbhd, hd._nbhd_size, hd._size) == [1, 2, 4]

		lookup_offset = calcsize(hd._pack_fmt) * 3
		_, nbhd = unpack_from(hd._pack_fmt, hd._lookup_table, lookup_offset)
		assert hd._get_displaced_neighbors(3, nbhd, hd._nbhd_size, hd._size) == [3]

		lookup_offset = calcsize(hd._pack_fmt) * 6
		_, nbhd = unpack_from(hd._pack_fmt, hd._lookup_table, lookup_offset)
		assert hd._get_displaced_neighbors(6, nbhd, hd._nbhd_size, hd._size) == [6, 7]

	else:
		with pytest.raises(ValueError):
			hd._get_displaced_neighbors(-1, 0, hd._nbhd_size, hd._size)

		with pytest.raises(ValueError):
			hd._get_displaced_neighbors(10, 0, hd._nbhd_size, hd._size)

		for i in range(6):
			hd[i] = "test_get_displaced_neighbors_{}".format(i)

		for i in range(6):
			lookup_offset = calcsize(hd._pack_fmt) * i
			_, nbhd = unpack_from(hd._pack_fmt, hd._lookup_table, lookup_offset)
			assert hd._get_displaced_neighbors(i, nbhd, hd._nbhd_size, hd._size) == [i]


@given(dict_keys)
def test_lookup(key):
	hd = HopscotchDict()

	hd[7] = "test_lookup_7"
	hd[15] = "test_lookup_15"

	assert hd._lookup(7) == (7, 0)
	assert hd._lookup(15) == (0, 1)

	del hd[7]
	del hd[15]

	lookup_idx = abs(hash(key)) % hd._size
	hd[key] = True
	assert hd._lookup(key)[0] == lookup_idx


@pytest.mark.parametrize("scenario", ["missing", "free"],
	ids = ["missing-key", "neighbor-previously-freed"])
def test_lookup_fails(scenario):
	hd = HopscotchDict()

	if scenario == "missing":
		assert hd._lookup("test_lookup") == (None, None)

	elif scenario == "free":
		hd[4] = "test_lookup"
		hd._set_lookup_index_info(4, data=hd.FREE_ENTRY)

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


@given(integers(), integers())
def test_set_neighbor(lookup_idx, nbhd_idx):
	hd = HopscotchDict()
	hd["test_set_neighbor"] = True

	if lookup_idx < 0 or nbhd_idx < 0 or lookup_idx >= hd._size or nbhd_idx >= hd._nbhd_size:
		with pytest.raises(ValueError):
			hd._set_neighbor(lookup_idx, nbhd_idx)
	else:
		hd._set_neighbor(lookup_idx, nbhd_idx)
		_, neighbors = hd._get_lookup_index_info(lookup_idx)
		assert (lookup_idx + nbhd_idx) % hd._size in neighbors

	lookup_idx, _ = hd._lookup("test_set_neighbor")
	_, neighbors = hd._get_lookup_index_info(lookup_idx)
	if len(neighbors) != hd._nbhd_size:
		for i in range(8):
			hd._set_neighbor(lookup_idx, i)
		assert len(hd._get_lookup_index_info(lookup_idx)[1]) == hd._nbhd_size


def test_clear():
	hd = HopscotchDict()

	for i in range(256):
		hd["test_clear_{}".format(i)] = i

	hd.clear()

	assert hd._count == 0
	assert hd._size == 8
	assert hd._nbhd_size == 8

	assert len(hd._keys) == 0
	assert len(hd._values) == 0

	for lookup_idx in range(hd._size):
		data_idx, neighbors = hd._get_lookup_index_info(lookup_idx)
		assert data_idx == hd.FREE_ENTRY
		assert len(neighbors) == 0


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
		expected_lookup_idx = abs(hash(key)) % hd._size
		_, neighbors = hd._get_lookup_index_info(expected_lookup_idx)
		lookup_idx, _ = hd._lookup(key)
		assert lookup_idx in neighbors


@pytest.mark.parametrize("scenario",
	["overwrite", "density_resize", "snr", "bnr", "ovw_err", "ins_err", "key_coll"],
	ids = ["overwrite", "density-resize", "small-nbhd-resize",
		   "big-nbhd-resize", "overwrite-error", "insert-error",
		   "degenerate-key-collision"])
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

	elif scenario == "key_coll":
		small_key = -1 % 2 ** 33
		large_key = -1 % 2 ** 34

		hd[small_key] = "test_setitem_key_coll_small"
		hd[large_key] = "test_setitem_key_coll_large"

		assert hd._size == 8
		assert hd[small_key] == "test_setitem_key_coll_small"
		assert hd[large_key] == "test_setitem_key_coll_large"



@pytest.mark.parametrize("scenario", ["found", "missing"],
	ids = ["found-key", "missing-key"])
def test_delitem(scenario):
	hd = HopscotchDict()

	if scenario == "found":
		for i in range(1, 7):
			hd[i] = "test_delitem_{}".format(i)

		for key in hd._keys:
			_, data_idx = hd._lookup(key)
			assert data_idx == key - 1

		del hd[6]

		for key in hd._keys:
			_, data_idx = hd._lookup(key)
			assert data_idx == key - 1

		del hd[2]

		_, data_idx = hd._lookup(1)
		assert data_idx == 0

		_, data_idx = hd._lookup(3)
		assert data_idx == 2

		_, data_idx = hd._lookup(4)
		assert data_idx == 3

		_, data_idx = hd._lookup(5)
		assert data_idx == 1

		del hd[3]

		_, data_idx = hd._lookup(1)
		assert data_idx == 0

		_, data_idx = hd._lookup(4)
		assert data_idx == 2

		_, data_idx = hd._lookup(5)
		assert data_idx == 1

		for key in copy(hd._keys):
			del hd[key]

		assert len(hd) == 0

		for i in range(hd._size):
			data_idx, neighbors = hd._get_lookup_index_info(i)
			assert data_idx == hd.FREE_ENTRY
			assert len(neighbors) == 0

	elif scenario == "missing":
		with pytest.raises(KeyError):
			del hd["test_delitem"]

@given(sample_dict)
@seed(262902792531650980708949300196033766230)
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


class HopscotchStateMachine(RuleBasedStateMachine):
	def __init__(self):
		super(HopscotchStateMachine, self).__init__()
		self.d = HopscotchDict()

	def teardown(self):
		keys = list(self.d.keys())

		for key in keys:
			del self.d[key]

	@invariant()
	def valid_neighborhoods(self):
		for lookup_idx in range(self.d._size):
			_, neighbors = self.d._get_lookup_index_info(lookup_idx)
			for neighbor in neighbors:
				data_idx = self.d._get_lookup_index_info(neighbor)[0]
				assert abs(hash(self.d._keys[data_idx])) % self.d._size == lookup_idx

	@invariant()
	def no_missing_data(self):
		assert len(self.d._keys) == len(self.d._values)

	@invariant()
	def bounded_density(self):
		if self.d._count > 0:
			assert self.d._count / self.d._size <= self.d.MAX_DENSITY

	@rule(k=dict_keys, v=dict_values)
	def add_entry(self, k, v):
		self.d[k] = v

	@rule(k=dict_keys)
	def remove_entry(self, k):
		if k not in self.d._keys:
			with pytest.raises(KeyError):
				del self.d[k]
		else:
			del self.d[k]

HopscotchStateMachine.TestCase.settings = settings(max_examples=50)
test_hopscotch_dict = HopscotchStateMachine.TestCase
