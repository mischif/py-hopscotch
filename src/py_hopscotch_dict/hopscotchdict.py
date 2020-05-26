# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from __future__ import division

from array import array
from collections.abc import MutableMapping
from struct import calcsize, pack, pack_into, unpack_from
from sys import maxsize, version_info


class HopscotchDict(MutableMapping):

	# Prevent default creation of __dict__, which should save space if many
	# instances of HopscotchDict are used at once
	__slots__ = ("_count", "_keys", "_lookup_table", "_nbhd_size", "_pack_fmt",
				 "_size", "_values")

	# Python ints are signed, add one to get word length
	MAX_NBHD_SIZE = maxsize.bit_length() + 1

	# Only allow neighborhood sizes that match word lengths
	ALLOWED_NBHD_SIZES = {8, 16, 32, 64}

	# Sentinel value used in indices table to denote we can put value here
	FREE_ENTRY = -1

	# Maximum allowed density before resizing
	MAX_DENSITY = 0.8

	@staticmethod
	def _get_displaced_neighbors(lookup_idx, nbhd, nbhd_size, max_size):
		"""
		Find the indices in _lookup_table that supposedly relate to a key that
		originally mapped to the given index, but were displaced during some
		previous _free_up call

		:param lookup_idx: The index in _lookup_table to find displaced neighbors for
		:param nbhd: The neighborhood at lookup_idx
		:param nbhd_size: The size of the given neighborhood
		:param max_size: The current maximum size of the dict

		:return: (list) Indices in _lookup_table that supposedly have data that would
						be stored at lookup_idx were it empty at the time of insertion
		"""
		if lookup_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif lookup_idx >= max_size:
			raise ValueError(u"Index {0} outside array".format(lookup_idx))

		result = []

		for i in range(nbhd_size):
			if nbhd & (1 << i) > 0:
				result.append((lookup_idx + i) % max_size)

		return result

	@staticmethod
	def _make_lookup_table(table_size):
		"""
		Make the array that holds the indices into _keys/_values and the
		neighborhoods for each index

		:param table_size: The number of entries of the returned table

		:return: (bytearray) The desired table
		"""
		if table_size < 0:
			raise ValueError(u"Lookup table cannot have negative length")

		table_log_size = table_size.bit_length()

		if table_log_size < 8:
			struct_fmt = "b B"
		elif table_log_size < 16:
			struct_fmt = ">h H"
		elif table_log_size < 32:
			struct_fmt = ">i I"
		else:
			struct_fmt = ">l L"

		return bytearray(pack(struct_fmt, HopscotchDict.FREE_ENTRY, 0) * table_size), struct_fmt

	def _clear_neighbor(self, lookup_idx, nbhd_idx):
		"""
		Set the given neighbor for the given index as unoccupied, with the neighborhood
		index 0 representing the given index

		:param lookup_idx: The index in _lookup_table
		:param nbhd_idx: The neighbor in the neighborhood of _lookup_table to set unoccupied
		"""
		if lookup_idx < 0 or nbhd_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError(u"Index {0} outside array".format(lookup_idx))
		elif nbhd_idx >= self._nbhd_size:
			raise ValueError(u"Trying to clear neighbor outside neighborhood")

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		value_idx, nbhd = unpack_from(self._pack_fmt, self._lookup_table, lookup_offset)

		nbhd &= ~(1 << nbhd_idx)

		pack_into(self._pack_fmt, self._lookup_table, lookup_offset, value_idx, nbhd)

	def _free_up(self, target_idx):
		"""
		Create an opening in the neighborhood of the given index by moving data
		from a neighbor out to one of its neighbors

		:param target_idx: The index in _lookup_table to find an oppening in its
						   nieighborhood for
		"""
		if target_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif target_idx >= self._size:
			raise ValueError(u"Index {0} outside array".format(target_idx))

		# Attempting to free up an index that has an open neighbor should be a no-op
		if self._get_open_neighbor(target_idx) is not None:
			return

		data_idx, _ = self._get_lookup_index_info(target_idx)
		entry_expected_idx = abs(hash(self._keys[data_idx])) % self._size

		# It is possible the entry in _lookup_table at target_idx is a displaced
		# neighbor of some prior index; if that's the case see if there is an
		# open neighbor of that prior index that the entry at target_idx can be
		# shifted to
		if entry_expected_idx != target_idx:
			nearest_neighbor = self._get_open_neighbor(entry_expected_idx)

			if nearest_neighbor is not None:
				target_nbhd_idx = (target_idx - entry_expected_idx) % self._size
				nearest_nbhd_idx = (nearest_neighbor - entry_expected_idx) % self._size

				self._set_lookup_index_info(nearest_neighbor, data=data_idx)
				self._set_lookup_index_info(target_idx, data=self.FREE_ENTRY)
				self._set_neighbor(entry_expected_idx, nearest_nbhd_idx)
				self._clear_neighbor(entry_expected_idx, target_nbhd_idx)
				# I used to clear the target_idx neighbor when the entry in target_idx
				# was displaced, but don't remember why; I'll keep a commented form of
				# that code for now in case it breaks something in testing
				# self._clear_neighbor(target_idx, 0)
				return

		# Walking down the array for an empty spot and shuffling entries around is
		# the only way
		lookup_idx = target_idx + self._nbhd_size
		while target_idx + self._nbhd_size <= lookup_idx < self._size:
			nearest_neighbor = self._get_open_neighbor(lookup_idx)

			# None of the next _nbhd_size - 1 locations in _lookup_table are empty
			if nearest_neighbor is None:
				lookup_idx += self._nbhd_size
				continue

			# Go _nbhd_size - 1 locations back in _lookup_table from the open location
			# to find a neighbor that can be displaced into the open location
			for idx in range(1, self._nbhd_size + 1):
				idx = (nearest_neighbor - self._nbhd_size + idx) % self._size
				_, idx_neighbors = self._get_lookup_index_info(idx)

				closest_idx = None
				if len(idx_neighbors) > 0:
					min_neighbor_idx = min(idx_neighbors, key=lambda i: (i - idx) % self._size)
					if (min_neighbor_idx - idx) % self._size < (nearest_neighbor - idx) % self._size:
						closest_idx = min_neighbor_idx

				# There is an entry before the open location which can be shuffled into
				# the open location
				if closest_idx is not None:
					data_idx, _ = self._get_lookup_index_info(closest_idx)
					self._set_lookup_index_info(nearest_neighbor, data=data_idx)
					self._set_lookup_index_info(closest_idx, data=self.FREE_ENTRY)

					closest_nbhd_idx = (closest_idx - idx) % self._size
					nearest_nbhd_idx = (nearest_neighbor - idx) % self._size
					self._set_neighbor(idx, nearest_nbhd_idx)
					self._clear_neighbor(idx, closest_nbhd_idx)
					lookup_idx = closest_idx
					break

				# If the last index before the open index has no displaced neighbors
				# or its closest one is after the open index, every index between the
				# given index and the open index is filled with data displaced from other indices,
				# and the invariant cannot be maintained without a resize
				elif idx == nearest_neighbor - 1:
					raise RuntimeError((u"No space available before open index"))

			# If the index that had its data punted is inside the target index's neighborhood,
			# the success condition has been attained
			if (lookup_idx - target_idx) % self._size < self._nbhd_size:
				return

		# No open indices exist between the given index and the end of the array
		raise RuntimeError(u"Could not open index while maintaining invariant")

	def _get_lookup_index_info(self, lookup_idx):
		"""
		Get the index into _keys/_values and the neighborhood at the given index
		of _lookup_table

		:param lookup_idx: the index to find info for

		:return: (tuple) The index into _keys/_values (or the empty sentinel),
						 and a list of all indices that have data related to
						 keys which would be stored at the given index
		"""
		if lookup_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError(u"Index {0} outside array".format(lookup_idx))

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		data_idx, nbhd = unpack_from(self._pack_fmt, self._lookup_table, lookup_offset)
		neighbors = self._get_displaced_neighbors(lookup_idx, nbhd, self._nbhd_size, self._size)
		return data_idx, neighbors

	def _get_open_neighbor(self, lookup_idx):
		"""
		Find the first index in the neighborhood of the given index that is not
		in use

		:param lookup_idx: The index in _lookup_table to find an open neighbor for

		:return: (int) The index in _lookup_table nearest to the given index not
					   currently in use
		"""
		if lookup_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError(u"Index {0} outside array".format(lookup_idx))

		result = None

		for idx in range(self._nbhd_size):
			idx = (lookup_idx + idx) % self._size
			data_idx, _ = self._get_lookup_index_info(idx)

			if data_idx == self.FREE_ENTRY:
				result = idx
				break

		return result

	def _lookup(self, key):
		"""
		Find the indices in _lookup_table and _keys that corresponds to the given key

		:param key: The key to search for in the dict

		:return: (tuple) The index in _lookup_table that holds the index to _keys for
						 the given key and the index to _keys, or None for both if the
						 key has not been inserted
		"""
		data_idx = None
		lookup_idx = abs(hash(key)) % self._size

		_, neighbors = self._get_lookup_index_info(lookup_idx)

		for neighbor in neighbors:
			neighbor_data_idx, _ = self._get_lookup_index_info(neighbor)

			if neighbor_data_idx < 0:
				raise RuntimeError((
					u"Index {0} has supposed displaced neighbor that points to "
					u"free index").format(lookup_idx))

			if self._keys[neighbor_data_idx] == key:
					data_idx = neighbor_data_idx
					lookup_idx = neighbor
					break

		if data_idx is None:
			lookup_idx = None

		return (lookup_idx, data_idx)

	def _resize(self, new_size):
		"""
		Resize the dict and relocate the current entries

		:param new_size: The desired new size of the dict
		"""
		# Dict size is a power of two to make modulo operations quicker
		if new_size & new_size - 1:
			raise ValueError(u"New size for dict not a power of 2")

		# Neighborhoods must be at least as large as the base-2 logarithm of
		# the dict size

		# 2**k requires k+1 bits to represent, so subtract one
		resized_nbhd_size = new_size.bit_length() - 1

		if resized_nbhd_size > self._nbhd_size:
			if resized_nbhd_size > self.MAX_NBHD_SIZE:
				raise ValueError(
					u"Resizing requires too-large neighborhood")
			self._nbhd_size = min(s for s in self.ALLOWED_NBHD_SIZES if s >= resized_nbhd_size)

		self._size = new_size
		self._lookup_table, self._pack_fmt = self._make_lookup_table(self._size)

		for data_idx, key in enumerate(self._keys):
			expected_lookup_idx = abs(hash(key)) % self._size

			nearest_neighbor = self._get_open_neighbor(expected_lookup_idx)
			if nearest_neighbor is None:
				self._free_up(expected_lookup_idx)
				nearest_neighbor = self._get_open_neighbor(expected_lookup_idx)
			nbhd_idx = (nearest_neighbor - expected_lookup_idx) % self._size
			self._set_neighbor(expected_lookup_idx, nbhd_idx)
			self._set_lookup_index_info(nearest_neighbor, data=data_idx)

	def _set_lookup_index_info(self, lookup_idx, data=None, nbhd=None):
		"""
		Update the given index of _lookup_table with new information

		:param lookup_idx: Index in _lookup_table to update
		:param data: New index into _keys/_values, or None to leave alone
		:param nbhd: New neighborhood information, or None to leave alone
		"""
		if lookup_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError(u"Index {0} outside array".format(lookup_idx))

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		data_idx, neighbors = unpack_from(self._pack_fmt, self._lookup_table, lookup_offset)

		if data is not None:
			data_idx = data

		if nbhd is not None:
			neighbors = nbhd

		pack_into(self._pack_fmt, self._lookup_table, lookup_offset, data_idx, neighbors)

	def _set_neighbor(self, lookup_idx, nbhd_idx):
		"""
		Set the given neighbor for the given index as occupied, with the neighborhood
		index 0 representing the given index

		:param lookup_idx: The index in _lookup_table
		:param nbhd_idx: The neighbor in the neighborhood of lookup_idx to set occupied
		"""
		if lookup_idx < 0 or nbhd_idx < 0:
			raise ValueError(u"Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError(u"Index {0} outside array".format(lookup_idx))
		elif nbhd_idx >= self._nbhd_size:
			raise ValueError(u"Trying to clear neighbor outside neighborhood")

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		value_idx, nbhd = unpack_from(self._pack_fmt, self._lookup_table, lookup_offset)

		nbhd |= (1 << nbhd_idx)

		pack_into(self._pack_fmt, self._lookup_table, lookup_offset, value_idx, nbhd)

	def clear(self):
		"""
		Remove all the data from the dict and return it to its original size
		"""
		# The total size of main dict, including empty spaces
		self._size = 8

		# The number of entries in the dict
		self._count = 0

		# The maximum number of neighbors to check if a key isn't
		# in its expected index
		self._nbhd_size = 8

		# Stored values
		if hasattr(self, "_values"):
			del self._values
		self._values = []

		# Stored keys
		if hasattr(self, "_keys"):
			del self._keys
		self._keys = []

		# Main table, storing auxiliary index and neighbors for each index
		if hasattr(self, "_lookup_table"):
			del self._lookup_table
		self._lookup_table, self._pack_fmt = self._make_lookup_table(self._size)

	def copy(self):
		"""
		Create a new instance with all items inserted
		"""
		out = HopscotchDict()

		for key in self._keys:
			out[key] = self.__getitem__(key)

		return out

	def get(self, key, default=None):
		"""
		Retrieve the value corresponding to the specified key, returning the
		default value if not found

		:param key: The key to retrieve data from
		:param default: The value to return if the specified key does not exist

		:returns: The value in the dict if the specified key exists;
							the default value if it does not
		"""
		out = default
		try:
			out = self.__getitem__(key)
		except KeyError:
			pass
		return out

	def has_key(self, key):
		"""
		Check if the given key exists

		:param key: The key to check for existence

		:returns: True if the key exists; False if it does not
		"""
		return self.__contains__(key)

	def keys(self):
		"""
		An iterator over all keys in the dict

		:returns: An iterator over self._keys
		"""
		return iter(self._keys)

	def values(self):
		"""
		An iterator over all values in the dict

		:returns: An iterator over self._values
		"""
		return iter(self._values)

	def items(self):
		"""
		An iterator over all `(key, value)` pairs

		:returns: An iterator over the `(key, value)` pairs
		"""
		return zip(self._keys, self._values)

	def pop(self, key, default=None):
		"""
		Return the value associated with the given key and removes it if the key
		exists; returns the given default value if the key does not exist;
		errors if the key does not exist and no default value was given

		:param key: The key to search for
		:param default: The value to return if the given key does not exist

		:returns: The value associated with the key if it exists, the default value
							if it does not
		"""
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
		"""
		Remove an arbitrary `(key, value)` pair if one exists, erroring otherwise

		:returns: An arbitrary `(key, value)` pair from the dict if one exists
		"""
		if not len(self):
			raise KeyError
		else:
			key = self._keys[-1]
			val = self.pop(self._keys[-1])
			return (key, val)

	def setdefault(self, key, default=None):
		"""
		Return the value associated with the given key if it exists, set the value
		associated with the given key to the default value if it does not

		:param key: The key to search for
		:param default: The value to insert if the key does not exist

		:returns: The value associated with the given key if it exists, the default
							value otherwise
		"""
		try:
			return self.__getitem__(key)
		except KeyError:
			self.__setitem__(key, default)
			return default

	def __init__(self, *args, **kwargs):
		"""
		Create a new instance with any specified values
		"""
		# Use clear function to do initial setup for new tables
		if not hasattr(self, "_size"):
			self.clear()

		self.update(*args, **kwargs)

	def __getitem__(self, key):
		"""
		Retrieve the value associated with the given key, erroring if the key does
		not exist

		:param key: The key to search for

		:returns: The value associated with the given key
		"""
		_, idx = self._lookup(key)
		if idx is not None:
			return self._values[idx]
		else:
			raise KeyError(key)

	def __setitem__(self, key, value):
		"""
		Map the given key to the given value, overwriting any previously-stored
		value if it exists

		:param key: The key to set
		:param value: The value to map the key to
		"""
		# The index key should map to in _lookup_table if it hasn't been evicted
		expected_lookup_idx = abs(hash(key)) % self._size

		# The index of the key in _keys and its related value in _values
		_, data_idx = self._lookup(key)

		# Overwrite an existing key with new data
		if data_idx is not None:
			self._keys[data_idx] = key
			self._values[data_idx] = value
			if not (len(self._keys) == len(self._values)):
				raise RuntimeError((
					u"Number of keys {0}; "
					u"number of values {1}; ").format(
						len(self._keys),
						len(self._values)))
			return

		# If there is an empty neighbor of expected_lookup_idx,
		# the entry for the new key/value can be stored there
		nearest_neighbor = self._get_open_neighbor(expected_lookup_idx)
		if nearest_neighbor is not None:
			nbhd_idx = (nearest_neighbor - expected_lookup_idx) % self._size
			self._set_neighbor(expected_lookup_idx, nbhd_idx)
			self._set_lookup_index_info(nearest_neighbor, data=self._count)
			self._keys.append(key)
			self._values.append(value)
			self._count += 1

		else:
			# Free up a neighbor of the expected index to accomodate the new key/value
			try:
				self._free_up(expected_lookup_idx)

			# No way to keep neighborhood invariant, must resize first
			except RuntimeError:
				if self._size < 2**16:
					self._resize(self._size * 4)
				else:
					self._resize(self._size * 2)

			# There should now be an available neighbor of the expected index, try again
			finally:
				self.__setitem__(key, value)
				return

		if len(self._keys) != len(self._values):
			raise RuntimeError((
				u"Number of keys {0}; "
				u"number of values {1}; ").format(
					len(self._keys),
					len(self._values)))

		if self._count / self._size >= self.MAX_DENSITY:
			if self._size < 2**16:
				self._resize(self._size * 4)
			else:
				self._resize(self._size * 2)

	def __delitem__(self, key):
		"""
		Remove the value the given key maps to
		"""
		# The index key should map to in _lookup_table if it hasn't been evicted
		expected_lookup_idx = abs(hash(key)) % self._size

		# The index key actually maps to in _lookup_table,
		# and the index its related value maps to in _values
		lookup_idx, data_idx = self._lookup(key)

		# Key not in dict
		if data_idx is None:
			raise KeyError(key)

		else:
			# If the key and its associated value aren't the last entries in their respective lists,
			# swap with the last entries to not leave a hole in said lists
			if data_idx != self._count - 1:
				tail_key = self._keys[-1]
				tail_val = self._values[-1]
				tail_lookup_idx, tail_data_idx = self._lookup(tail_key)

				# Move the data to be removed to the end of each list and update indices
				self._keys[data_idx] = tail_key
				self._values[data_idx] = tail_val
				self._set_lookup_index_info(tail_lookup_idx, data=data_idx)

			# Update the neighborhood of the index the key to be removed is
			# supposed to point to, since the key to be removed must be
			# somewhere in it

			nbhd_idx = (lookup_idx - expected_lookup_idx) % self._size
			self._clear_neighbor(expected_lookup_idx, nbhd_idx)

			# Remove the last item from the variable tables, either the actual
			# data to be removed or what was originally at the end before
			# it was copied over the data to be removed
			del self._keys[-1]
			del self._values[-1]
			self._set_lookup_index_info(lookup_idx, data=self.FREE_ENTRY)
			self._count -= 1

	def __contains__(self, key):
		"""
		Check if the given key exists

		:returns: True if the key exists, False otherwise
		"""
		_, idx = self._lookup(key)
		return idx is not None

	def __eq__(self, other):
		"""
		Check if the given object is equivalent to this dict

		:param other: The object to test for equality to this dict

		:returns: True if the given object is equivalent to this dict,
							False otherwise
		"""
		if not isinstance(other, MutableMapping):
			return False

		if len(self) != len(other):
			return False

		if set(self._keys) ^ set(other.keys()):
			return False

		return all(map(lambda key: type(self[key]) == type(other[key]) and self[key] == other[key],
					   self._keys))

	def __iter__(self):
		"""
		Return an iterator over the keys

		:returns An iterator over the keys
		"""
		return iter(self._keys)

	def __len__(self):
		"""
		Return the number of items currently stored

		:returns: The number of items currently stored
		"""
		return self._count

	def __ne__(self, other):
		"""
		Check if the given object is not equivalent to this dict

		:param other: The object to test for equality to this dict

		:returns: True if the given object is not equivalent to this dict,
							False otherwise
		"""
		return not self.__eq__(other)

	def __repr__(self):
		"""
		Return a representation that could be used to create an equivalent dict
		using `eval()`

		:returns: A string that could be used to create an equivalent representation
		"""
		return u"HopscotchDict({0})".format(self.__str__())

	def __reversed__(self):
		"""
		Return an iterator over the keys in reverse order

		:returns: An iterator over the keys in reverse order
		"""
		return reversed(self._keys)

	def __str__(self):
		"""
		Return a simpler representation of the items in the dict

		:returns: A string containing all items in the dict
		"""
		stringified = []

		for (key, val) in getattr(self, 'iteritems', self.items)():
			stringified.append(u"{0!r}: {1!r}".format(key, val))

		return u"{{{0}}}".format(u", ".join(stringified))
