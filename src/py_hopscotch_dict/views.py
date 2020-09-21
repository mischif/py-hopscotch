# encoding: utf-8

################################################################################
#                              py-hopscotch-dict                               #
#    Full-featured `dict` replacement with guaranteed constant-time lookups    #
#                       (C) 2017, 2019-2020 Jeremy Brown                       #
#       Released under version 3.0 of the Non-Profit Open Source License       #
################################################################################

from typing import (Any,
					AbstractSet,
					Collection,
					Hashable,
					ItemsView,
					Iterator,
					KeysView,
					MappingView,
					Tuple,
					TYPE_CHECKING,
					Union,
					ValuesView
					)

if TYPE_CHECKING:											  # pragma: no cover
	from py_hopscotch_dict.hopscotchdict import HopscotchDict


class HDView(MappingView):
	def __init__(self, source: "HopscotchDict") -> None:
		self._source = source

	def __len__(self) -> int:
		return self._source._count

	def __iter__(self) -> Union[Iterator[Hashable], Iterator[Any]]:
		result = None

		if isinstance(self, HDKeys):
			result = iter(self._source._keys)

		else:
			result = iter(self._source._values)

		return result

	def __reversed__(self) -> Union[Iterator[Hashable], Iterator[Any]]:
		result = None

		if isinstance(self, HDKeys):
			result = reversed(self._source._keys)

		else:
			result = reversed(self._source._values)

		return result

	def __contains__(self, query: Any) -> bool:
		result = False

		if isinstance(self, HDKeys):
			_, idx = self._source._lookup(query)
			result = True if idx is not None else False

		elif isinstance(query, tuple) and isinstance(self, HDItems):
			k, v = query

			_, idx = self._source._lookup(k)
			if idx is not None:
				result = True if self._source._values[idx] == v else False

		elif isinstance(self, HDValues):
			result = True if query in self._source._values else False

		return result

	def __le__(self, other: AbstractSet[Any]) -> bool:
		result = False

		if self._source._count <= len(other) and isinstance(self, HDKeys):
			result = all(k in other for k in self._source._keys)

		elif self._source._count <= len(other) and isinstance(self, HDItems):
			result = all(i in other for i in zip(self._source._keys, self._source._values))

		return result

	def __ge__(self, other: AbstractSet[Any]) -> bool:
		result = False

		if self._source._count >= len(other) and isinstance(self, HDKeys):
			result = all(k in self._source._keys for k in other)

		elif self._source._count >= len(other) and isinstance(self, HDItems):
			items = set(zip(self._source._keys, self._source._values))
			result = all(i in items for i in other)

		return result

	def issubset(self, other: Collection[Any]) -> bool:
		result = False

		if self._source._count <= len(other) and isinstance(self, HDKeys):
			result = all(k in other for k in self._source._keys)

		elif self._source._count <= len(other) and isinstance(self, HDItems):
			result = all(i in other for i in zip(self._source._keys, self._source._values))

		return result

	def issuperset(self, other: Collection[Any]) -> bool:
		result = False

		if self._source._count >= len(other) and isinstance(self, HDKeys):
			result = all(k in self._source._keys for k in other)

		elif self._source._count >= len(other) and isinstance(self, HDItems):
			items = set(zip(self._source._keys, self._source._values))
			result = all(i in items for i in other)

		return result

	def union(self, *others: Collection[Any]) -> AbstractSet[Any]:
		result = set()

		if isinstance(self, HDKeys):
			result.update(self._source._keys)

		elif isinstance(self, HDItems):
			result.update(zip(self._source._keys, self._source._values))

		for other_set in others:
			result.update(other_set)

		return result

	def intersection(self, *others: Collection[Any]) -> AbstractSet[Any]:
		result = set()

		if isinstance(self, HDKeys):
			result.update(self._source._keys)

		elif isinstance(self, HDItems):
			result.update(zip(self._source._keys, self._source._values))

		for other_set in others:
			result = result.intersection(other_set)

		return result

	def difference(self, *others: Collection[Any]) -> AbstractSet[Any]:
		result = set()

		if isinstance(self, HDKeys):
			result.update(self._source._keys)

		elif isinstance(self, HDItems):
			result.update(zip(self._source._keys, self._source._values))

		for other_set in others:
			result = result.difference(other_set)

		return result

	def symmetric_difference(self, *others: Collection[Any]) -> AbstractSet[Any]:
		result = set()

		if isinstance(self, HDKeys):
			result.update(self._source._keys)

		elif isinstance(self, HDItems):
			result.update(zip(self._source._keys, self._source._values))

		for other_set in others:
			result = result.symmetric_difference(other_set)

		return result


class HDKeys(HDView, KeysView[Hashable]):
	def __init__(self, source: "HopscotchDict") -> None:
		super(HDKeys, self).__init__(source)


class HDValues(HDView, ValuesView[Any]):
	def __init__(self, source: "HopscotchDict") -> None:
		super(HDValues, self).__init__(source)


class HDItems(HDView, ItemsView[Hashable, Any]):
	def __init__(self, source: "HopscotchDict") -> None:
		super(HDItems, self).__init__(source)

	def __iter__(self) -> Iterator[Tuple[Hashable, Any]]:
		return zip(self._source._keys, self._source._values)

	def __reversed__(self) -> Iterator[Tuple[Hashable, Any]]:
		return zip(reversed(self._source._keys), reversed(self._source._values))
