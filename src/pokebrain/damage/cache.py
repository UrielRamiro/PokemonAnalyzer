from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Protocol

from pokebrain.damage.engine import DamageEngine
from pokebrain.damage.engine import serialize_damage_request
from pokebrain.damage.models import DamageRequest, DamageResult


@dataclass(frozen=True, slots=True)
class DamageCacheKey:
    engine_version_hash: str
    generation: int
    format_id: str
    attacker_hash: str
    defender_hash: str
    move_id: str
    field_hash: str


@dataclass(frozen=True, slots=True)
class DamageEngineVersion:
    showdown_commit: str = "unknown"
    calculator_version: str = "unknown"
    bridge_schema_version: int = 1


@dataclass(slots=True)
class DamageEngineMetrics:
    requested_calculations: int = 0
    unique_calculations: int = 0
    l1_cache_hits: int = 0
    same_scenario_hits: int = 0
    cross_scenario_hits: int = 0
    l2_cache_hits: int = 0
    cache_misses: int = 0
    bridge_batches: int = 0
    bridge_requests: int = 0
    total_bridge_time_ms: float = 0.0


class DamageCache(Protocol):
    def get(self, key: DamageCacheKey) -> DamageResult | None:
        ...

    def set(self, key: DamageCacheKey, result: DamageResult) -> None:
        ...


class SearchDamageCache:
    def __init__(self) -> None:
        self._values: dict[DamageCacheKey, DamageResult] = {}
        self._owners: dict[DamageCacheKey, str | None] = {}

    def get(self, key: DamageCacheKey) -> DamageResult | None:
        return self._values.get(key)

    def owner(self, key: DamageCacheKey) -> str | None:
        return self._owners.get(key)

    def set(self, key: DamageCacheKey, result: DamageResult, owner: str | None = None) -> None:
        self._values[key] = result
        self._owners[key] = owner

    def clear(self) -> None:
        self._values.clear()
        self._owners.clear()


class LruDamageCache:
    def __init__(self, maximum_entries: int = 50_000) -> None:
        self.maximum_entries = maximum_entries
        self._values: OrderedDict[DamageCacheKey, DamageResult] = OrderedDict()

    def get(self, key: DamageCacheKey) -> DamageResult | None:
        result = self._values.get(key)
        if result is not None:
            self._values.move_to_end(key)
        return result

    def set(self, key: DamageCacheKey, result: DamageResult) -> None:
        self._values[key] = result
        self._values.move_to_end(key)
        while len(self._values) > self.maximum_entries:
            self._values.popitem(last=False)


class CachedDamageEngine:
    def __init__(
        self,
        inner: DamageEngine,
        l1_cache: SearchDamageCache | None = None,
        l2_cache: DamageCache | None = None,
        engine_version: DamageEngineVersion | None = None,
    ) -> None:
        self.inner = inner
        self.l1_cache = l1_cache or SearchDamageCache()
        self.l2_cache = l2_cache or LruDamageCache()
        self.engine_version = engine_version or DamageEngineVersion()
        self.metrics = DamageEngineMetrics()
        self.current_scenario_id: str | None = None

    def set_scenario_id(self, scenario_id: str | None) -> None:
        self.current_scenario_id = scenario_id

    def calculate(self, request: DamageRequest) -> DamageResult:
        return self.calculate_many((request,))[0]

    def calculate_many(self, requests: tuple[DamageRequest, ...]) -> tuple[DamageResult, ...]:
        self.metrics.requested_calculations += len(requests)
        keys = tuple(build_cache_key(request, self.engine_version) for request in requests)
        resolved: dict[DamageCacheKey, DamageResult] = {}
        missing: dict[DamageCacheKey, DamageRequest] = {}

        for key, request in zip(keys, requests):
            l1_result = self.l1_cache.get(key)
            if l1_result is not None:
                self.metrics.l1_cache_hits += 1
                owner = self.l1_cache.owner(key)
                if self.current_scenario_id is not None and owner is not None and owner != self.current_scenario_id:
                    self.metrics.cross_scenario_hits += 1
                else:
                    self.metrics.same_scenario_hits += 1
                resolved[key] = l1_result
                continue

            l2_result = self.l2_cache.get(key)
            if l2_result is not None:
                self.metrics.l2_cache_hits += 1
                self.l1_cache.set(key, l2_result, owner=self.current_scenario_id)
                resolved[key] = l2_result
                continue

            missing.setdefault(key, request)

        if missing:
            self.metrics.cache_misses += len(missing)
            self.metrics.unique_calculations += len(missing)
            missing_keys = tuple(missing)
            missing_requests = tuple(missing.values())
            started_at = time.perf_counter()
            if hasattr(self.inner, "calculate_many"):
                results = self.inner.calculate_many(missing_requests)
            else:
                results = tuple(self.inner.calculate(request) for request in missing_requests)
            self.metrics.total_bridge_time_ms += (time.perf_counter() - started_at) * 1000
            self.metrics.bridge_batches += 1
            self.metrics.bridge_requests += len(missing_requests)

            for key, result in zip(missing_keys, results):
                self.l1_cache.set(key, result, owner=self.current_scenario_id)
                self.l2_cache.set(key, result)
                resolved[key] = result

        return tuple(resolved[key] for key in keys)

    def begin_search_scope(self, *, clear_l1: bool = True, reset_metrics: bool = True) -> None:
        if clear_l1:
            self.l1_cache.clear()
        if reset_metrics:
            self.metrics = DamageEngineMetrics()
        self.current_scenario_id = None


BatchCachedDamageEngine = CachedDamageEngine


def build_cache_key(
    request: DamageRequest,
    engine_version: DamageEngineVersion | None = None,
) -> DamageCacheKey:
    payload = serialize_damage_request(request)
    defender_payload = dict(payload["defender"])
    defender_payload.pop("currentHp", None)
    version = engine_version or DamageEngineVersion()
    return DamageCacheKey(
        engine_version_hash=stable_hash(
            {
                "showdown_commit": version.showdown_commit,
                "calculator_version": version.calculator_version,
                "bridge_schema_version": version.bridge_schema_version,
            }
        ),
        generation=request.generation,
        format_id=request.format_id,
        attacker_hash=_stable_json(payload["attacker"]),
        defender_hash=_stable_json(defender_payload),
        move_id=request.move_id,
        field_hash=_stable_json(payload["field"]),
    )


def _stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def stable_hash(value: object) -> str:
    payload = _stable_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
