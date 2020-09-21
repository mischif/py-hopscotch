# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from array import array
from functools import partial
from struct import calcsize, pack, pack_into, unpack_from
from sys import maxsize, version_info
from typing import (Any,
					Callable,
					cast,
					Hashable,
					ItemsView,
					Iterator,
					KeysView,
					List,
					MutableMapping,
					Optional,
					Set,
					Tuple,
					Union,
					ValuesView
					)

from py_hopscotch_dict.views import HDItems, HDKeys, HDValues


class HopscotchDict(MutableMapping[Hashable, Any]):
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
	def _get_displaced_neighbors(lookup_idx: int,
								 nbhd: int,
								 nbhd_size: int,
								 max_size: int) -> List[int]:
		"""
		Find the indices in _lookup_table that supposedly relate to a key that
		originally mapped to the given index, but were displaced during some
		previous _free_up call

		:param lookup_idx: The index in _lookup_table to find displaced
						   neighbors for
		:param nbhd: The neighborhood at lookup_idx
		:param nbhd_size: The size of the given neighborhood
		:param max_size: The current maximum size of the dict

		:return: Indices in _lookup_table that supposedly have data that would
				 be stored at lookup_idx were it empty at the time of insertion
		"""
		if lookup_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif lookup_idx >= max_size:
			raise ValueError("Index {0} outside array".format(lookup_idx))

		result = []

		for i in range(nbhd_size):
			if nbhd & (1 << i) > 0:
				result.append((lookup_idx + i) % max_size)

		return result

	@staticmethod
	def _make_lookup_table(table_size: int) -> Tuple[bytearray, str]:
		"""
		Make the array that holds the indices into _keys/_values and the
		neighborhoods for each index

		:param table_size: The number of entries of the returned table

		:return: The desired table as a `bytearray` and the corresponding
				 struct string necessary to read it
		"""
		if table_size < 0:
			raise ValueError("Lookup table cannot have negative length")

		table_log_size = table_size.bit_length()

		if table_log_size < 8:
			struct_fmt = "b B"
		elif table_log_size < 16:
			struct_fmt = ">h H"
		elif table_log_size < 32:
			struct_fmt = ">i I"
		else:
			struct_fmt = ">l L"								  # pragma: no cover

		return (bytearray(pack(struct_fmt,
							   HopscotchDict.FREE_ENTRY,
							   0) * table_size),
				struct_fmt)

	def clear(self) -> None:
		"""
		Remove all the data from the dict and return it to its original size
		"""
		self._lookup_table: bytearray
		self._pack_fmt: str

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
		self._values: List[Any] = []

		# Stored keys
		if hasattr(self, "_keys"):
			del self._keys
		self._keys: List[Hashable] = []

		# Main table, storing auxiliary index and neighbors for each index
		if hasattr(self, "_lookup_table"):
			del self._lookup_table
		self._lookup_table, self._pack_fmt = self._make_lookup_table(self._size)

	def _clear_neighbor(self, lookup_idx: int, nbhd_idx: int) -> None:
		"""
		Set the given neighbor for the given index as unoccupied,
		with the neighborhood index 0 representing the given index

		:param lookup_idx: The index in _lookup_table
		:param nbhd_idx: The neighbor in the neighborhood of _lookup_table to
						 set unoccupied
		"""
		if lookup_idx < 0 or nbhd_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError("Index {0} outside array".format(lookup_idx))
		elif nbhd_idx >= self._nbhd_size:
			raise ValueError("Trying to clear neighbor outside neighborhood")

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		value_idx, nbhd = unpack_from(self._pack_fmt,
									  self._lookup_table,
									  lookup_offset)

		nbhd &= ~(1 << nbhd_idx)

		pack_into(self._pack_fmt,
				  self._lookup_table,
				  lookup_offset,
				  value_idx,
				  nbhd)

	def _free_up(self, target_idx: int) -> None:
		"""
		Create an opening in the neighborhood of the given index by moving data
		from a neighbor out to one of its neighbors

		:param target_idx: The index in _lookup_table to find an oppening in its
						   nieighborhood for
		"""
		if target_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif target_idx >= self._size:
			raise ValueError("Index {0} outside array".format(target_idx))

		# Attempting to free an index with an open neighbor is a no-op
		if self._get_open_neighbor(target_idx) is not None:
			return

		def _disp_dist(curr: int, exp: int) -> int:
			return (curr - exp) % self._size

		data_idx, _ = self._get_lookup_index_info(target_idx)
		entry_expected_idx = abs(hash(self._keys[data_idx])) % self._size

		# It is possible the entry in _lookup_table at target_idx is a displaced
		# neighbor of some prior index; if that's the case see if there is an
		# open neighbor of that prior index that the entry at target_idx can be
		# shifted to
		if entry_expected_idx != target_idx:
			nearest_neighbor = self._get_open_neighbor(entry_expected_idx)

			if nearest_neighbor is not None:
				target_nbhd_idx = ((target_idx - entry_expected_idx)
									% self._size)
				nearest_nbhd_idx = ((nearest_neighbor - entry_expected_idx)
									 % self._size)

				self._set_lookup_index_info(nearest_neighbor, data=data_idx)
				self._set_lookup_index_info(target_idx, data=self.FREE_ENTRY)
				self._set_neighbor(entry_expected_idx, nearest_nbhd_idx)
				self._clear_neighbor(entry_expected_idx, target_nbhd_idx)
				# I used to clear the target_idx neighbor when the entry in
				# target_idx was displaced, but don't remember why; I'll keep a
				# commented form of that code for now in case it breaks
				# something in testing
				# self._clear_neighbor(target_idx, 0)
				return

		# Walking down the array for an empty spot and shuffling entries around
		# is the only way
		lookup_idx = target_idx + self._nbhd_size
		while target_idx + self._nbhd_size <= lookup_idx < self._size:
			nearest_neighbor = self._get_open_neighbor(lookup_idx)

			# All of the next _nbhd_size - 1 locations in _lookup_table are full
			if nearest_neighbor is None:
				lookup_idx += self._nbhd_size
				continue

			# Go _nbhd_size - 1 locations back in _lookup_table from the open
			# location to find a neighbor that can be displaced into the opening
			for idx in range(1, self._nbhd_size + 1):
				idx = (nearest_neighbor - self._nbhd_size + idx) % self._size
				_, idx_neighbors = self._get_lookup_index_info(idx)
				_dd = partial(_disp_dist, exp=idx)

				entry_idx = None
				if len(idx_neighbors) > 0:
					min_neighbor_idx = min(idx_neighbors, key=_dd)
					if _dd(min_neighbor_idx) < _dd(nearest_neighbor):
						entry_idx = min_neighbor_idx

				# There is an entry before the open location which can be
				# shuffled into the open location
				if entry_idx is not None:
					data_idx, _ = self._get_lookup_index_info(entry_idx)
					self._set_lookup_index_info(nearest_neighbor, data=data_idx)
					self._set_lookup_index_info(entry_idx, data=self.FREE_ENTRY)

					closest_nbhd_idx = _dd(entry_idx)
					nearest_nbhd_idx = _dd(nearest_neighbor)
					self._set_neighbor(idx, nearest_nbhd_idx)
					self._clear_neighbor(idx, closest_nbhd_idx)
					lookup_idx = entry_idx
					break

				# If the last index before the open index has no displaced
				# neighbors or its closest one is after the open index, every
				# index between the given index and the open index is filled
				# with data displaced from other indices, and the invariant
				# cannot be maintained without a resize
				elif idx == nearest_neighbor - 1:
					raise RuntimeError(("No space available before open index"))

			# If the index that had its data punted is inside the target index's
			# neighborhood, the success condition has been attained
			if _disp_dist(lookup_idx, target_idx) < self._nbhd_size:
				return

		# No open indices exist between the given index and the end of the array
		raise RuntimeError("Could not open index while maintaining invariant")

	def _get_lookup_index_info(self,
							   lookup_idx: int) -> Tuple[int, List[int]]:
		"""
		Get the index into _keys/_values and the neighborhood at the given index
		of _lookup_table

		:param lookup_idx: the index to find info for

		:return: The index into _keys/_values (or the sentinel), and a list of
				 all indices that have data related to keys which would be
				 stored at the given index
		"""
		if lookup_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError("Index {0} outside array".format(lookup_idx))

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx

		data_idx, nbhd = unpack_from(self._pack_fmt,
									 self._lookup_table,
									 lookup_offset)

		neighbors = self._get_displaced_neighbors(lookup_idx,
												  nbhd,
												  self._nbhd_size,
												  self._size)
		return data_idx, neighbors

	def _get_open_neighbor(self, lookup_idx: int) -> Optional[int]:
		"""
		Find the first neighbor of the given index that is not in use

		:param lookup_idx: _lookup_table index to find an open neighbor for

		:return: The index in _lookup_table nearest to the given index not
				 currently in use
		"""
		if lookup_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError("Index {0} outside array".format(lookup_idx))

		result = None

		for idx in range(self._nbhd_size):
			idx = (lookup_idx + idx) % self._size
			data_idx, _ = self._get_lookup_index_info(idx)

			if data_idx == self.FREE_ENTRY:
				result = idx
				break

		return result

	def _lookup(self, key: Hashable) -> Tuple[Optional[int], Optional[int]]:
		"""
		Find the indices in _lookup_table and _keys that correspond to the given
		key

		:param key: The key to search for in the dict

		:return: The index in _lookup_table that holds the index to _keys for
				 the given key and the index to _keys, or None for both if the
				 key has not been inserted
		"""
		data_idx = None
		lookup_idx = None

		_, neighbors = self._get_lookup_index_info(abs(hash(key)) % self._size)

		for neighbor in neighbors:
			nbr_data_idx, _ = self._get_lookup_index_info(neighbor)

			if nbr_data_idx < 0:
				raise RuntimeError((
					"Index {0} has supposed displaced neighbor that points to "
					"free index").format(abs(hash(key)) % self._size))

			if self._keys[nbr_data_idx] == key:
					data_idx = nbr_data_idx
					lookup_idx = neighbor
					break

		if data_idx is None:
			lookup_idx = None

		return (lookup_idx, data_idx)

	def _resize(self, new_size: int) -> None:
		"""
		Resize the dict and relocate the current entries

		:param new_size: The desired new size of the dict
		"""
		# Dict size is a power of two to make modulo operations quicker
		if new_size & new_size - 1:
			raise ValueError("New size for dict not a power of 2")

		# Neighborhoods must be at least as large as the base-2 logarithm of
		# the dict size

		# 2**k requires k+1 bits to represent, so subtract one
		resized_nbhd_size = new_size.bit_length() - 1

		if resized_nbhd_size > self._nbhd_size:
			if resized_nbhd_size > self.MAX_NBHD_SIZE:
				raise ValueError("Resizing requires too-large neighborhood")
			self._nbhd_size = min(s for s in self.ALLOWED_NBHD_SIZES
								  if s >= resized_nbhd_size)

		self._size = new_size
		self._lookup_table, self._pack_fmt = self._make_lookup_table(self._size)

		for data_idx, key in enumerate(self._keys):
			expected_lookup_idx = abs(hash(key)) % self._size

			nearest_neighbor = self._get_open_neighbor(expected_lookup_idx)
			if nearest_neighbor is None:
				self._free_up(expected_lookup_idx)
				nearest_neighbor = self._get_open_neighbor(expected_lookup_idx)
				nearest_neighbor = cast(int, nearest_neighbor)
			nbhd_idx = ((nearest_neighbor - expected_lookup_idx)
						 % self._size)
			self._set_neighbor(expected_lookup_idx, nbhd_idx)
			self._set_lookup_index_info(nearest_neighbor, data=data_idx)

	def _set_lookup_index_info(self,
							   lookup_idx: int,
							   data: Optional[int]=None,
							   nbhd: Optional[int]=None) -> None:
		"""
		Update the given index of _lookup_table with new information

		:param lookup_idx: Index in _lookup_table to update
		:param data: New index into _keys/_values, or None to leave alone
		:param nbhd: New neighborhood information, or None to leave alone
		"""
		if lookup_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError("Index {0} outside array".format(lookup_idx))

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		data_idx, neighbors = unpack_from(self._pack_fmt,
										  self._lookup_table,
										  lookup_offset)

		if data is not None:
			data_idx = data

		if nbhd is not None:
			neighbors = nbhd

		pack_into(self._pack_fmt,
				  self._lookup_table,
				  lookup_offset,
				  data_idx,
				  neighbors)

	def _set_neighbor(self, lookup_idx: int, nbhd_idx: int) -> None:
		"""
		Set the given neighbor for the given index as occupied, with the
		index 0 representing the given index

		:param lookup_idx: The index in _lookup_table
		:param nbhd_idx: The neighbor in the neighborhood to set occupied
		"""
		if lookup_idx < 0 or nbhd_idx < 0:
			raise ValueError("Indexes cannot be negative")
		elif lookup_idx >= self._size:
			raise ValueError("Index {0} outside array".format(lookup_idx))
		elif nbhd_idx >= self._nbhd_size:
			raise ValueError("Trying to clear neighbor outside neighborhood")

		lookup_offset = calcsize(self._pack_fmt) * lookup_idx
		value_idx, nbhd = unpack_from(self._pack_fmt,
									  self._lookup_table,
									  lookup_offset)

		nbhd |= (1 << nbhd_idx)

		pack_into(self._pack_fmt,
				  self._lookup_table,
				  lookup_offset,
				  value_idx,
				  nbhd)

	def copy(self) -> MutableMapping[Hashable, Any]:
		"""
		Create a new instance with all items inserted
		"""
		out = HopscotchDict()

		for key in self._keys:
			out[key] = self.__getitem__(key)

		return out

	def get(self, key: Hashable, default: Any=None) -> Any:
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

	def has_key(self, key: Hashable) -> bool:
		"""
		Check if the given key exists

		:param key: The key to check for existence

		:returns: True if the key exists; False if it does not
		"""
		return self.__contains__(key)

	def keys(self) -> KeysView[Hashable]:
		"""
		An iterator over all keys in the dict

		:returns: An iterator over self._keys
		"""
		return HDKeys(self)

	def values(self) -> ValuesView[Any]:
		"""
		An iterator over all values in the dict

		:returns: An iterator over self._values
		"""
		return HDValues(self)

	def items(self) -> ItemsView[Hashable, Any]:
		"""
		An iterator over all `(key, value)` pairs

		:returns: An iterator over the `(key, value)` pairs
		"""
		return HDItems(self)

	def pop(self, key: Hashable, default: Any=None) -> Any:
		"""
		Return the value associated with the given key and removes it if the key
		exists; returns the given default value if the key does not exist;
		errors if the key does not exist and no default value was given

		:param key: The key to search for
		:param default: The value to return if the given key does not exist

		:returns: The value associated with the key if it exists, the default
				  value if it does not
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

	def popitem(self) -> Tuple[Hashable, Any]:
		"""
		Remove an arbitrary `(key, value)` pair if one exists,
		erroring otherwise

		:returns: An arbitrary `(key, value)` pair from the dict if one exists
		"""
		if not len(self):
			raise KeyError
		else:
			key = self._keys[-1]
			val = self.pop(self._keys[-1])
			return (key, val)

	def setdefault(self, key: Hashable, default: Any=None) -> Any:
		"""
		Return the value associated with the given key if it exists,
		set the value associated with the given key to the default value if it
		does not

		:param key: The key to search for
		:param default: The value to insert if the key does not exist

		:returns: The value associated with the given key if it exists,
				  the default value otherwise
		"""
		try:
			return self.__getitem__(key)
		except KeyError:
			self.__setitem__(key, default)
			return default

	def __init__(self, *args: Any, **kwargs: Any) -> None:
		"""
		Create a new instance with any specified values
		"""
		# Use clear function to do initial setup for new tables
		if not hasattr(self, "_size"):
			self.clear()

		self.update(*args, **kwargs)

	def __getitem__(self, key: Hashable) -> Any:
		"""
		Retrieve the value associated with the given key,
		erroring if the key does not exist

		:param key: The key to search for

		:returns: The value associated with the given key
		"""
		_, idx= self._lookup(key)
		if idx is not None:
			return self._values[idx]
		else:
			raise KeyError(key)

	def __setitem__(self, key: Hashable, value: Any) -> None:
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
					"Number of keys {0}; "
					"number of values {1}; ").format(
						len(self._keys),
						len(self._values)))
			return

		# If there is an empty neighbor of expected_lookup_idx,
		# the entry for the new key/value can be stored there
		nearest_nbr = self._get_open_neighbor(expected_lookup_idx)
		if nearest_nbr is not None:
			nbhd_idx = (nearest_nbr - expected_lookup_idx) % self._size
			self._set_neighbor(expected_lookup_idx, nbhd_idx)
			self._set_lookup_index_info(nearest_nbr, data=self._count)
			self._keys.append(key)
			self._values.append(value)
			self._count += 1

		else:
			# Free up a neighbor of the expected index to accomodate the new
			# item
			try:
				self._free_up(expected_lookup_idx)

			# No way to keep neighborhood invariant, must resize first
			except RuntimeError:
				if self._size < 2**16:
					self._resize(self._size * 4)
				else:
					self._resize(self._size * 2)

			# There should now be an available neighbor of the expected index,
			# try again
			finally:
				self.__setitem__(key, value)
				return

		if len(self._keys) != len(self._values):
			raise RuntimeError((
				"Number of keys {0}; "
				"number of values {1}; ").format(
					len(self._keys),
					len(self._values)))

		if self._count / self._size >= self.MAX_DENSITY:
			if self._size < 2**16:
				self._resize(self._size * 4)
			else:
				self._resize(self._size * 2)

	def __delitem__(self, key: Hashable) -> None:
		"""
		Remove the given key from the dict and its associated value

		:param key: The key to remove from the dict 
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
			# If the key and its associated value aren't the last entries in
			# their respective lists, swap with the last entries to not leave a
			# hole in said lists
			lookup_idx = cast(int, lookup_idx)

			if data_idx != self._count - 1:
				tail_key = self._keys[-1]
				tail_val = self._values[-1]
				tail_lookup_idx, tail_data_idx = self._lookup(tail_key)
				tail_lookup_idx = cast(int, tail_lookup_idx)
				# Move the data to be removed to the end of each list and update
				# indices
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

	def __contains__(self, key: Hashable) -> bool:
		"""
		Check if the given key exists

		:returns: True if the key exists, False otherwise
		"""
		_, idx = self._lookup(key)
		return idx is not None

	def __eq__(self, other: Any) -> bool:
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

		return all(self[k] == other[k] and type(self[k]) == type(other[k])
				   for k in self._keys)

	def __iter__(self) -> Iterator[Hashable]:
		"""
		Return an iterator over the keys

		:returns An iterator over the keys
		"""
		return iter(self._keys)

	def __len__(self) -> int:
		"""
		Return the number of items currently stored

		:returns: The number of items currently stored
		"""
		return self._count

	def __ne__(self, other: Any) -> bool:
		"""
		Check if the given object is not equivalent to this dict

		:param other: The object to test for equality to this dict

		:returns: True if the given object is not equivalent to this dict,
				  False otherwise
		"""
		return not self.__eq__(other)

	def __repr__(self) -> str:
		"""
		Return a representation that could be used to create an equivalent dict
		using `eval()`

		:returns: A string that could be used to create an equivalent
				  representation
		"""
		return "HopscotchDict({0})".format(self.__str__())

	def __reversed__(self) -> Iterator[Hashable]:
		"""
		Return an iterator over the keys in reverse order

		:returns: An iterator over the keys in reverse order
		"""
		return reversed(self._keys)

	def __str__(self) -> str:
		"""
		Return a simpler representation of the items in the dict

		:returns: A string containing all items in the dict
		"""
		stringified = []

		for (key, val) in self.items():
			stringified.append("{0!r}: {1!r}".format(key, val))

		return "{{{0}}}".format(", ".join(stringified))
