# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                               (C) 2019 Mischif                               #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from sys import version_info

import pytest

from hypothesis import given

from py_hopscotch_dict import HopscotchDict
from test import sample_dict


oldpython = pytest.mark.skipif(version_info.major > 2, reason="Requires Python 2.7 to test")


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
