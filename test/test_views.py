# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

import pytest

from hypothesis import example, given, seed, settings
from hypothesis.strategies import integers
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from py_hopscotch_dict import HopscotchDict
from test import dict_keys, dict_values, max_dict_entries, sample_dict


@given(sample_dict)
def test_keys(gen_dict):
	hd = HopscotchDict(gen_dict)
	keys = hd.keys()
	start_len = len(hd)

	assert len(keys) == start_len
	assert all(k in hd for k in keys)

	hd["test_keys"] = True

	assert len(keys) == start_len + 1
	assert "test_keys" in keys


@given(sample_dict)
def test_values(gen_dict):
	hd = HopscotchDict(gen_dict)
	vals = hd.values()
	start_len = len(hd)

	assert len(vals) == start_len
	assert all(v in hd._values for v in vals)

	hd["test_values"] = "test_values"

	assert len(vals) == start_len + 1
	assert "test_values" in vals


@given(sample_dict)
def test_items(gen_dict):
	hd = HopscotchDict(gen_dict)
	items = hd.items()
	start_len = len(hd)

	assert len(items) == start_len
	assert all(hd[k] == v for (k, v) in items)

	hd["test_items"] = True

	assert len(items) == start_len + 1
	assert ("test_items", True) in items


@given(sample_dict)
def test_reversed(gen_dict):
	hd = HopscotchDict(gen_dict)
	keys = hd.keys()
	vals = hd.values()
	items = hd.items()

	assert list(reversed(list(reversed(keys)))) == hd._keys
	assert list(reversed(list(reversed(vals)))) == hd._values
	for (i, (k, v)) in enumerate(reversed(list(reversed(items)))):
		assert k == hd._keys[i]
		assert v == hd._values[i]

	hd["test_keys"] = True


def test_subset():
	hd = HopscotchDict()
	keys = hd.keys()
	items = hd.items()

	hd["a"] = 1
	hd["b"] = 2
	hd["c"] = 3

	s1 = ["a", "b"]
	s2 = ["a", "b", "c"]
	s3 = ["a", "b", "c", "d"]

	s4 = [1, 2]
	s5 = [1, 2, 3]
	s6 = [1, 2, 3, 4]

	assert not keys <= set(s1)
	assert not keys.issubset(s1)

	assert keys <= set(s2)
	assert keys.issubset(s2)

	assert keys <= set(s3)
	assert keys.issubset(s3)

	assert not items <= set(list(zip(s1, s4)))
	assert not items.issubset(list(zip(s1, s4)))

	assert items <= set(list(zip(s2, s5)))
	assert items.issubset(list(zip(s2, s5)))

	assert items <= set(list(zip(s3, s6)))
	assert items.issubset(list(zip(s3, s6)))


def test_superset():
	hd = HopscotchDict()
	keys = hd.keys()
	items = hd.items()

	hd["a"] = 1
	hd["b"] = 2
	hd["c"] = 3

	s1 = ["a", "b"]
	s2 = ["a", "b", "c"]
	s3 = ["a", "b", "c", "d"]

	s4 = [1, 2]
	s5 = [1, 2, 3]
	s6 = [1, 2, 3, 4]

	assert keys >= set(s1)
	assert keys.issuperset(s1)

	assert keys >= set(s2)
	assert keys.issuperset(s2)

	assert not keys >= set(s3)
	assert not keys.issuperset(s3)

	assert items >= set(list(zip(s1, s4)))
	assert items.issuperset(list(zip(s1, s4)))

	assert items >= set(list(zip(s2, s5)))
	assert items.issuperset(list(zip(s2, s5)))

	assert not items >= set(list(zip(s3, s6)))
	assert not items.issuperset(list(zip(s3, s6)))


def test_union():
	hd = HopscotchDict()
	keys = hd.keys()
	items = hd.items()

	hd["a"] = 1
	hd["b"] = 2
	hd["c"] = 3

	s1 = ["a", "b"]
	s2 = ["a", "b", "c", "d"]

	s3 = [1, 2]
	s4 = [1, 2, 3, 4]

	assert keys | set(s1) == keys
	assert keys.union(s2) == set(s2)

	assert items | zip(s1, s3) == items
	assert items.union(zip(s2, s4)) == set(list(zip(s2, s4)))


def test_intersection():
	hd = HopscotchDict()
	keys = hd.keys()
	items = hd.items()

	hd["a"] = 1
	hd["b"] = 2
	hd["c"] = 3

	s1 = ["a", "b"]
	s2 = ["a", "b", "c", "d"]
	s3 = ["d", "e", "f"]

	s4 = [1, 2]
	s5 = [1, 2, 3, 4]
	s6 = [4, 5, 6]

	assert keys & set(s1) == set(s1)
	assert keys.intersection(s2) == keys

	assert items & zip(s1, s4) == set(zip(s1, s4))
	assert items.intersection(zip(s2, s5)) == items

	assert keys & set(s3) == set()
	assert keys.intersection(s3) == set()

	assert items & zip(s3, s6) == set()
	assert items.intersection(zip(s3, s6)) == set()


def test_difference():
	hd = HopscotchDict()
	keys = hd.keys()
	items = hd.items()

	hd["a"] = 1
	hd["b"] = 2
	hd["c"] = 3

	s1 = ["a", "b"]
	s2 = ["a", "b", "c", "d"]
	s3 = ["d", "e", "f"]

	s4 = [1, 2]
	s5 = [1, 2, 3, 4]
	s6 = [4, 5, 6]

	assert keys - set(s1) == {"c"}
	assert keys.difference(s2) == set()

	assert items - zip(s1, s4) == {("c", 3)}
	assert items.difference(zip(s2, s5)) == set()

	assert keys - set(s3) == keys
	assert keys.difference(s3) == keys

	assert items - zip(s3, s6) == items
	assert items.difference(zip(s3, s6)) == items


def test_symmetric_difference():
	hd = HopscotchDict()
	keys = hd.keys()
	items = hd.items()

	hd["a"] = 1
	hd["b"] = 2
	hd["c"] = 3

	s1 = ["a", "b"]
	s2 = ["a", "b", "c", "d"]
	s3 = ["d", "e", "f"]

	s4 = [1, 2]
	s5 = [1, 2, 3, 4]
	s6 = [4, 5, 6]

	assert keys ^ set(s1) == {"c"}
	assert keys.symmetric_difference(s2) == {"d"}

	assert items ^ zip(s1, s4) == {("c", 3)}
	assert items.symmetric_difference(zip(s2, s5)) == {("d", 4)}

	assert keys ^ set(s3) == keys | set(s3)
	assert keys.symmetric_difference(s3) == keys | set(s3)

	assert items ^ zip(s3, s6) == items | zip(s3, s6)
	assert items.symmetric_difference(zip(s3, s6)) == items | zip(s3, s6)
