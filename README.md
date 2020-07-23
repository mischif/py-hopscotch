py-hopscotch-dict
=================

[![GitHub Workflow](https://img.shields.io/github/workflow/status/mischif/py-hopscotch-dict/Pipeline?logo=github&style=for-the-badge)](https://github.com/mischif/py-hopscotch-dict/actions)
[![Codecov](https://img.shields.io/codecov/c/github/mischif/py-hopscotch-dict?logo=codecov&style=for-the-badge)](https://codecov.io/gh/mischif/py-hopscotch-dict)
[![Python Versions](https://img.shields.io/pypi/pyversions/py-hopscotch-dict?style=for-the-badge)](https://pypi.org/project/py-hopscotch-dict/)
[![Package Version](https://img.shields.io/pypi/v/py-hopscotch-dict?style=for-the-badge)](https://pypi.org/project/py-hopscotch-dict/)
[![License](https://img.shields.io/pypi/l/py-hopscotch-dict?style=for-the-badge)](https://pypi.org/project/py-hopscotch-dict/)

py-hopscotch-dict is a package that contains a replacement for the standard Python `dict` which implements the concepts of [hopscotch hashing](https://en.wikipedia.org/wiki/Hopscotch_hashing), as explained in the [foundational paper](http://mcg.cs.tau.ac.il/papers/disc2008-hopscotch.pdf).

Hopscotch hashing provides a number of benefits over the methods used in the standard `dict` implementation, most notably that insertions, deletions and lookups have an expected O(1) runtime.

py-hopscotch-dict has not been tested in a concurrent environment and thusly cannot be guaranteed to function correctly in conjunction with multi-threading, across multiple processes or in an asynchronous environment

Usage
-----

	>>> from py_hopscotch_dict import HopscotchDict
	>>> d = HopscotchDict()
	>>> d["test"] = True
	>>> d
	HopscotchDict({'test': True})
