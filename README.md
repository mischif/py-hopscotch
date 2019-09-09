py-hopscotch-dict
=================

[![Travis](https://img.shields.io/travis/mischif/py-hopscotch-dict.svg)](https://travis-ci.org/mischif/py-hopscotch-dict)
[![Codecov](https://img.shields.io/codecov/c/github/mischif/py-hopscotch-dict.svg)](https://codecov.io/gh/mischif/py-hopscotch-dict)

py-hopscotch-dict is a package that contains a replacement for the standard Python `dict` which implements the concepts of [hopscotch hashing](https://en.wikipedia.org/wiki/Hopscotch_hashing), as explained in the [foundational paper](http://mcg.cs.tau.ac.il/papers/disc2008-hopscotch.pdf).

Hopscotch hashing provides a number of benefits over the methods used in the standard `dict` implementation, most notably that additions, deletions and lookups have an expected O(1) runtime.

py-hopscotch-dict is implemented to replicate a [Python 3.6-style `dict`](https://youtu.be/npw4s1QTmPg), and as such brings additional effects to Python 2.7 beyond those of hopscotch hashing.

py-hopscotch-dict has not been tested in a concurrent environment and thusly cannot be guaranteed to function correctly in conjunction with multi-threading, across multiple processes or in an asynchronous environment

Usage
-----

	>>> from py_hopscotch_dict import HopscotchDict
	>>> d = HopscotchDict()
	>>> d["test"] = True
	>>> d
	HopscotchDict({'test': True})
