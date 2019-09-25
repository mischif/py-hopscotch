# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                               (C) 2019 Mischif                               #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from io import open
from os.path import abspath, dirname, join

from py_hopscotch_dict.hopscotchdict import HopscotchDict

module_root = dirname(abspath(__file__))
package_root = dirname(module_root)

with open(join(package_root, "VERSION"), encoding="utf-8") as version_file:
	__version__ = version_file.read().strip()
