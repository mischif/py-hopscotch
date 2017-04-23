from __future__ import division
from array import array
from copy import copy
from collections import MutableMapping
from itertools import izip
from sys import maxint

class HopscotchDict(MutableMapping):

	# Python ints are signed, add one to get word length
	MAX_NBHD_SIZE = maxint.bit_length() + 1

	# Only allow neighborhood sizes that match word lengths
	ALLOWED_NBHD_SIZES = {8, 16, 32, 64}

	# Sentinel value used in indices table to denote we can put value here
	FREE_ENTRY = -1

	# Maximum allowed density before resizing
	MAX_DENSITY = 0.8

	@staticmethod
	def _make_indices(size):
		if size <= 2**7: return array("b", [HopscotchDict.FREE_ENTRY]) * size
		if size <= 2**15: return array("h", [HopscotchDict.FREE_ENTRY]) * size
		if size <= 2**31: return array("i", [HopscotchDict.FREE_ENTRY]) * size
		return array("l", [HopscotchDict.FREE_ENTRY]) * size

	@staticmethod
	def _make_nbhds(nbhd_size, array_size):
		if nbhd_size == 8: return array("B", [0]) * array_size
		if nbhd_size == 16: return array("H", [0]) * array_size
		if nbhd_size == 32: return array("I", [0]) * array_size
		return array("L", [0]) * array_size

	def _clear_neighbor(self, idx, nbhd_idx):
		if nbhd_idx >= self._nbhd_size:
			raise ValueError("Trying to clear neighbor outside neighborhood")

		self._nbhds[idx] &= ~(1 << self._nbhd_size - nbhd_idx - 1)

	def _free_up(self, idx):
		act_idx = idx
		while act_idx < self._size:

			if self._indices[act_idx] != self.FREE_ENTRY:
				act_idx += 1
				continue

			# If there is an open index in the given index's neighborhood,
			# move the pointer in the given index to the open index and update
			# the given index's neighborhood
			elif act_idx - idx < self._nbhd_size:
				# idx is the index to open up
				# orig_idx is the index the key in self._indices[idx] is
				# supposed to hash to
				# act_idx is the open index
				orig_idx = self._hashes[self._indices[idx]] % self._size
				self._indices[act_idx] = self._indices[idx]
				self._set_neighbor(orig_idx, act_idx - orig_idx)
				self._indices[idx] = self.FREE_ENTRY
				self._clear_neighbor(idx, 0)
				self._clear_neighbor(orig_idx, idx - orig_idx)
				return

			# The open index is too far away, so find the closest index to the
			# given index to free up and repeat until the given index is opened
			else:
				for i in xrange(max(idx, act_idx - self._nbhd_size) + 1, act_idx):

					# If the last index before the open index has no displaced
					# neighbors or its closest one is after the open index,
					# every index between the given index and the open index is
					# filled with data displaced from other indices, and the
					# invariant cannot be maintained without a resize
					if i == act_idx - 1:
						if (not self._nbhds[i]
							or min(self._get_displaced_neighbors(i)) > act_idx):
								raise Exception((
										"No space available before open index"))

					# If the index has displaced neighbors and one is before the open
					# index, move the data in the neighbor into the open index
					if self._nbhds[i]:
						hop_idx = min(self._get_displaced_neighbors(i))
						if hop_idx < act_idx:
							self._indices[act_idx] = self._indices[hop_idx]
							self._indices[hop_idx] = self.FREE_ENTRY
							self._set_neighbor(i, act_idx - i)
							self._clear_neighbor(i, hop_idx - i)
							act_idx = hop_idx
							break
					else:
						continue

		# No open indices exist between the given index and the end of the array
		raise Exception("Could not open index while maintaining invariant")

	def _get_displaced_neighbors(self, idx):
		neighbors = []
		nbhd = self._nbhds[idx]

		for i in xrange(self._nbhd_size - 1, -1, -1):
			if nbhd & 1 << i:
				neighbors.append(idx + self._nbhd_size - i - 1)

		return neighbors

	def _lookup(self, key):
		retval = None
		hashed = abs(hash(key))

		for idx in self._get_displaced_neighbors(hashed % self._size):
			if idx >= self._size:
				raise AssertionError((
					"Index {0} has supposed displaced neighbor "
					"outside array").format(hashed % self._size))

			if self._indices[idx] < 0:
				raise AssertionError((
					"Index {0} has supposed displaced neighbor that points to "
					"free index").format(hashed % self._size))

			if (self._keys[self._indices[idx]] is key
				or self._hashes[self._indices[idx]] == hashed
				and self._keys[self._indices[idx]] == key):
					retval = idx
		return retval

	def _resize(self, new_size):
		# Dict size is a power of two to make modulo operations quicker
		if new_size & new_size - 1:
			raise AssertionError("New size for dict not a power of 2")

		# Neighborhoods must be at least as large as the base-2 logarithm of
		# the dict size

		# 2**k requires k+1 bits to represent, so subtract one
		resized_nbhd_size = new_size.bit_length() - 1

		# As long as the size of the dict isn't squared during resizing,
		# multiplying neighborhood size by 2 will be sufficient as long as the
		# result is less than a machine word
		if resized_nbhd_size > self._nbhd_size:
			if resized_nbhd_size > self.MAX_NBHD_SIZE:
				raise AssertionError(
					"Resizing requires too-large neighborhood")
			self._nbhd_size = min(s for s in self.ALLOWED_NBHD_SIZES if s >= resized_nbhd_size)

		self._nbhds = self._make_nbhds(self._nbhd_size, new_size)
		self._indices = self._make_indices(new_size)
		self._size = new_size


		# This works b/c the order of hashes is the same as the order of keys
		# and values
		for data_idx, hsh in enumerate(self._hashes):
			exp_idx = hsh % self._size

			if self._indices[exp_idx] == self.FREE_ENTRY:
				self._indices[exp_idx] = data_idx
				self._set_neighbor(exp_idx, 0)
			else:
				try:
					self._free_up(exp_idx)

				# If an index's neighborhood fills up during resizing, abandon
				# the current effort and resize to a bigger size
				except Exception:
					self._resize(self._size * 2)
					return
				else:
					self._indices[exp_idx] = data_idx
					self._set_neighbor(exp_idx, 0)


	def _set_neighbor(self, idx, nbhd_idx):
		if nbhd_idx >= self._nbhd_size:
			raise ValueError("Trying to clear neighbor outside neighborhood")

		self._nbhds[idx] |= (1 << self._nbhd_size - nbhd_idx - 1)

	def clear(self):
		# The total size of main dict, including empty spaces
		self._size = 8

		# The number of entries in the dict
		self._count = 0

		# The maximum number of neighbors to check if a key isn't
		# in its expected index
		self._nbhd_size = 8

		# Table that stores values associated with keys
		self._values = []

		# Table that stores actual keys
		self._keys = []

		# Table that stores hashes of keys
		self._hashes = []

		# Table that stores neighborhood info for each index
		# MSB: the given index; LSB: the index _nbhd_size - 1 away
		self._nbhds = self._make_nbhds(self._nbhd_size, self._size)

		# The main table, used to map keys to values
		self._indices = self._make_indices(self._size)

	def copy(self):
		out = HopscotchDict()

		for key in self._keys:
			out[key] = copy(self.__getitem__(key))

		return out

	def get(self, key, default=None):
		out = default
		try:
			out = self.__getitem__(key)
		except KeyError:
			pass
		return out

	def has_key(self, key):
		return self.__contains__(key)

	def items(self):
		return zip(self._keys, self._values)

	def iteritems(self):
		return izip(self._keys, self._values)

	def iterkeys(self):
		return self.__iter__()

	def itervalues(self):
		return iter(self._values)

	def keys(self):
		return self._keys

	def pop(self, key, default=None):
		out = default

		try:
			out = self.__getitem__(key)
		except KeyError:
			if default is None:
				raise
		else:
			self.__delitem__(key)

		return out

	def popitem(self):
		if not len(self):
			raise KeyError
		else:
			key = self._keys[-1]
			val = self.pop(self._keys[-1])
			return (key, val)

	def setdefault(self, key, default=None):
		try:
			return self.__getitem__(key)
		except KeyError:
			self.__setitem__(key, default)
			return default

	def values(self):
		return self._values

	def __init__(self, *args, **kwargs):

		# Use clear function to do initial setup for new tables
		if not hasattr(self, "_size"):
			self.clear()

		self.update(*args, **kwargs)

	def __getitem__(self, key):
		idx = self._lookup(key)
		if idx is not None:
			return self._values[self._indices[idx]]
		else:
			raise KeyError(key)

	def __setitem__(self, key, value):
		exp_idx = abs(hash(key)) % self._size
		act_idx = self._lookup(key)

		# Overwrite an existing key with new data
		if act_idx:
			if self._indices[act_idx] != self.FREE_ENTRY:
				self._keys[self._indices[act_idx]] = key
				self._values[self._indices[act_idx]] = value
				self._hashes[self._indices[act_idx]] = abs(hash(key))
				if not (len(self._keys) == len(self._values) == len(self._hashes)):
					raise AssertionError((
						"Number of keys {0}; "
						"number of values {1}; "
						"number of hashes {2}").format(
							len(self._keys),
							len(self._values),
							len(self._hashes)))
				return

			# If _lookup returns an index, but the index is free, there must
			# have been leftover data and something's gone wrong
			else:
				raise AssertionError("_lookup returned a previously-freed index")

		# Move existing data out of index to accomodate new data
		elif self._indices[exp_idx] != self.FREE_ENTRY:
			try:
				self._free_up(exp_idx)

			# No way to keep neighborhood invariant, resize and try again
			except Exception:
				if self._size < 2**16:
					self._resize(self._size * 4)
				else:
					self._resize(self._size * 2)

				self.__setitem__(key, value)
				return

		# Index never previously stored data or it was successfully moved,
		# Either way, add the new data to its expected index
		self._indices[exp_idx] = self._count
		self._keys.append(key)
		self._values.append(value)
		self._hashes.append(abs(hash(key)))
		self._set_neighbor(exp_idx, 0)
		self._count += 1
		if not (len(self._keys) == len(self._values) == len(self._hashes)):
			raise AssertionError((
				"Number of keys {0}; "
				"number of values {1}; "
				"number of hashes {2}").format(
					len(self._keys),
					len(self._values),
					len(self._hashes)))

		if self._count / self._size >= self.MAX_DENSITY:
			if self._size < 2**16:
				self._resize(self._size * 4)
			else:
				self._resize(self._size * 2)


	def __delitem__(self, key):
		act_idx = self._lookup(key)
		exp_idx = abs(hash(key)) % self._size

		if act_idx:
			# If the key's associated data isn't the last entry in their
			# respective lists, swap with the last entries to not leave a hole
			# in said tables and update the _indices pointer
			if self._indices[act_idx] != self._count:
				last_hash = self._hashes[-1]
				last_key = self._keys[-1]
				last_val = self._values[-1]
				last_idx = self._lookup(last_key)

				self._keys[self._indices[act_idx]] = last_key
				self._values[self._indices[act_idx]] = last_val
				self._hashes[self._indices[act_idx]] = last_hash
				self._indices[last_idx] = self._indices[act_idx]

			# Update the neighborhood of the index the key to be removed is
			# supposed to point to, since the key to be removed must be
			# somewhere in it

			# Checking if the actual index for the key is less than the expected
			# index is unneccessary because data is only displaced forward in
			# _indices
			if act_idx != exp_idx:
				self._clear_neighbor(exp_idx, act_idx - exp_idx)
			else:
				self._clear_neighbor(act_idx, 0)

			# Remove the last item from the variable tables, either the actual
			# data to be removed or what was originally at the end before
			# it was copied over the data to be removed
			self._keys.pop()
			self._hashes.pop()
			self._values.pop()
			self._indices[act_idx] = self.FREE_ENTRY
			self._count -= 1

		# Key not in dict
		else:
			raise KeyError(key)

	def __contains__(self, key):
		if isinstance(self._lookup(key), int):
			return True
		else:
			return False

	def __eq__(self, other):
		if not isinstance(other, MutableMapping):
			return False

		if len(self) != len(other):
			return False

		all_keys = set(self._keys).union(other.keys())
		if len(all_keys) != len(self):
			return False

		for key in all_keys:
			if (type(self[key]) != type(other[key])
				or self[key] != other[key]):
					return False
		return True

	def __iter__(self):
		return iter(self._keys)

	def __len__(self):
		return self._count

	def __neq__(self, other):
		return not self.__eq__(other)

	def __repr__(self):
		return "HopscotchDict({0!r})".format(self.items())

	def __reversed__(self):
		return reversed(self._keys)

	def __str__(self):
		return "{{{0}}}".format(
			", ".join("'{0!s}': {1!s}".format(*i) for i in self.iteritems()))
