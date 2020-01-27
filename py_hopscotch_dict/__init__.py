# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from io import open
from os.path import abspath, dirname, join

from py_hopscotch_dict.hopscotchdict import HopscotchDict

module_root = dirname(abspath(__file__))

with open(join(module_root, "VERSION"), encoding="utf-8") as version_file:
	__version__ = version_file.read().strip()
