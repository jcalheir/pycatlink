"""Fork addition: litter box visits, daily summaries and history statistics.

* Visits: parsed from the device "top 5" log (already refreshed every minute by
  pycatlink). New entries become events; the latest visit per cat is kept.
* Today: per-cat daily summary (``token/pet/health/v3/summarySimple``) every
  5 minutes - visits, pee, poop, average duration and weight, health status.
* History: long-term external statistics (``catlink:pet_<id>_<metric>``), one row
  per day at local midnight, back-filled from the cat's creation date and kept
  up to date hourly. Visible in statistics graphs (daily/weekly/monthly).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from pycatlink.const import HttpMethod

_LOGGER = logging.getLogger(__name__)

API_PET_SUMMARY = "token/pet/health/v3/summarySimple"
TODAY_REFRESH = timedelta(minutes=5)

KIND_PEE = "xixi"
KIND_POOP = "coco"
KIND_UNKNOWN = "desconhecido"
KINDS = [KIND_PEE, KIND_POOP, KIND_UNKNOWN]
KIND_LABELS = {KIND_PEE: "xixi", KIND_POOP: "cocó", KIND_UNKNOWN: "não identificado"}

# metric -> (has_sum, unit, unit_class, label)
HISTORY_METRICS: dict[str, tuple[bool, str | None, str | None, str]] = {
    "idas": (True, None, None, "idas à caixa"),
    "xixi": (True, None, None, "xixi"),
    "coco": (True, None, None, "cocó"),
    "duracao": (False, "s", "duration", "duração média"),
    "peso": (False, "kg", "mass", "peso médio"),
}


@dataclass
class Visit:
    """One litter box visit."""

    log_id: str
    pet_id: str | None
    kind: str
    weight_kg: float | None
    duration_s: int | None
    when: datetime

    def attributes(self) -> dict[str, Any]:
        """Attributes exposed on entities."""
        return {
            "tipo": self.kind,
            "peso_kg": self.weight_kg,
            "duracao_s": self.duration_s,
            "hora": self.when.isoformat(),
            "resumo": self.summary_text(),
        }

    def summary_text(self) -> str:
        """Human text, e.g. 'cocó · 1 min 47 s · 5,3 kg'."""
        parts = [KIND_LABELS.get(self.kind, self.kind)]
        if self.duration_s is not None:
            m, s = divmod(int(self.duration_s), 60)
            parts.append(f"{m} min {s} s" if m else f"{s} s")
        if self.weight_kg is not None:
            parts.append(f"{self.weight_kg:.1f} kg".replace(".", ","))
        return " · ".join(parts)


@dataclass
class DaySummary:
    """Daily toilet summary for one cat."""

    day: date
    visits: int = 0
    pee: int = 0
    poop: int = 0
    duration_avg_s: float | None = None
    weight_avg_kg: float | None = None
    health_status: str | None = None
    weight_status: str | None = None


@dataclass
class VisitState:
    """Visit-related state shared with entities."""

    last_visit: dict[str, Visit] = field(default_factory=dict)  # pet_id -> visit
    new_visits: list[Visit] = field(default_factory=list)  # since last update
    today: dict[str, DaySummary] = field(default_factory=dict)  # pet_id -> summary


def _kind(event: str | None) -> str:
    text = (event or "").lower()
    if "pee" in text or "urin" in text:
        return KIND_PEE
    if "poo" in text or "stool" in text or "feces" in text:
        return KIND_POOP
    return KIND_UNKNOWN


def _number(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def parse_log(log: Any, tz: ZoneInfo, now: datetime) -> Visit | None:
    """Convert a C08 log entry into a Visit (None for non-toilet entries)."""
    if (getattr(log, "type", None) or "").upper() != "WC" or not getattr(log, "id", None):
        return None
    try:
        hh, mm = (int(x) for x in (log.time or "").split(":")[:2])
    except ValueError:
        return None
    local_now = now.astimezone(tz)
    when = datetime.combine(local_now.date(), time(hh, mm), tz)
    if when > local_now + timedelta(minutes=2):
        when -= timedelta(days=1)
    pet_id = log.pet_id if log.pet_id and log.pet_id != "0" else None
    duration = _number(log.second_section)
    return Visit(
        log_id=str(log.id),
        pet_id=pet_id,
        kind=_kind(log.event),
        weight_kg=_number(log.first_section),
        duration_s=int(duration) if duration is not None else None,
        when=when,
    )


def parse_summary(day: date, response: dict[str, Any]) -> DaySummary:
    """Parse the summarySimple response."""
    toilet = (response.get("data") or {}).get("toilet") or {}
    weight = toilet.get("weightAvg")
    duration = toilet.get("durationAvg")
    return DaySummary(
        day=day,
        visits=int(toilet.get("times") or 0),
        pee=int(toilet.get("peed") or 0),
        poop=int(toilet.get("pood") or 0),
        duration_avg_s=round(float(duration), 1) if duration else None,
        weight_avg_kg=float(weight) if weight else None,
        health_status=toilet.get("healthStatus"),
        weight_status=toilet.get("weightStatus"),
    )


class VisitTracker:
    """Keeps visit state across coordinator updates."""

    def __init__(self, client: Any, tz: ZoneInfo) -> None:
        """Initialize."""
        self._client = client
        self.tz = tz
        self._seen: set[str] = set()
        self._initialised = False
        self._today_at: datetime | None = None
        self.state = VisitState()

    async def fetch_summary(self, pet_id: str, day: date) -> DaySummary:
        """Fetch one day's summary for one cat."""
        response = await self._client.request_with_auto_login(
            path=API_PET_SUMMARY,
            method=HttpMethod.GET,
            parameters={
                "petId": pet_id,
                "date": day.isoformat(),
                "sport": 1,
                "timezoneId": str(self.tz),
            },
        )
        return parse_summary(day, response)

    async def update(self, logs: list[Any], pet_ids: list[str], now: datetime) -> VisitState:
        """Process device logs and refresh today's summaries when due."""
        new: list[Visit] = []
        visits = [v for v in (parse_log(log, self.tz, now) for log in logs) if v]
        for visit in sorted(visits, key=lambda v: v.when):
            if visit.log_id in self._seen:
                continue
            self._seen.add(visit.log_id)
            if visit.pet_id:
                prev = self.state.last_visit.get(visit.pet_id)
                if prev is None or visit.when >= prev.when:
                    self.state.last_visit[visit.pet_id] = visit
            if self._initialised:
                new.append(visit)
        self._initialised = True
        self.state.new_visits = new

        if new or self._today_at is None or now - self._today_at >= TODAY_REFRESH:
            today = now.astimezone(self.tz).date()
            for pet_id in pet_ids:
                try:
                    self.state.today[pet_id] = await self.fetch_summary(pet_id, today)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("Today summary failed for pet %s: %s", pet_id, err)
            self._today_at = now
        return self.state


async def async_sync_history(hass: Any, tracker: VisitTracker, pets: dict[str, Any]) -> None:
    """Back-fill / extend daily external statistics for every cat."""
    from homeassistant.components.recorder import get_instance  # noqa: PLC0415
    from homeassistant.components.recorder.models import (  # noqa: PLC0415
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
    )
    from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
        async_add_external_statistics,
        get_last_statistics,
    )

    tz = tracker.tz
    yesterday = datetime.now(tz).date() - timedelta(days=1)
    recorder = get_instance(hass)

    for pet_id, pet in pets.items():
        name = getattr(pet, "pet_name", None) or f"Pet {pet_id}"
        ids = {m: f"catlink:pet_{pet_id}_{m}" for m in HISTORY_METRICS}
        last = await recorder.async_add_executor_job(
            get_last_statistics, hass, 1, ids["idas"], True, {"sum"}
        )
        sums = {m: 0.0 for m, spec in HISTORY_METRICS.items() if spec[0]}
        if last.get(ids["idas"]):
            start = (
                datetime.fromtimestamp(last[ids["idas"]][0]["start"], tz).date()
                + timedelta(days=1)
            )
            for metric in sums:
                prev = await recorder.async_add_executor_job(
                    get_last_statistics, hass, 1, ids[metric], True, {"sum"}
                )
                sums[metric] = float((prev.get(ids[metric]) or [{}])[0].get("sum") or 0.0)
        else:
            created = getattr(pet, "create_time", None)
            start = (
                datetime.fromtimestamp(created / 1000, tz).date()
                if created
                else yesterday - timedelta(days=365)
            )
            start = max(start, yesterday - timedelta(days=730))
        if start > yesterday:
            continue

        rows: dict[str, list[StatisticData]] = {m: [] for m in HISTORY_METRICS}
        day = start
        while day <= yesterday:
            try:
                summary = await tracker.fetch_summary(pet_id, day)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("History sync stopped at %s for %s: %s", day, name, err)
                break
            t0 = datetime.combine(day, time(0, 0), tz)
            for metric, value in (
                ("idas", summary.visits),
                ("xixi", summary.pee),
                ("coco", summary.poop),
            ):
                sums[metric] += value
                rows[metric].append(StatisticData(start=t0, state=value, sum=sums[metric]))
            if summary.duration_avg_s:
                v = summary.duration_avg_s
                rows["duracao"].append(StatisticData(start=t0, mean=v, min=v, max=v))
            if summary.weight_avg_kg:
                v = summary.weight_avg_kg
                rows["peso"].append(StatisticData(start=t0, mean=v, min=v, max=v))
            day += timedelta(days=1)
            await asyncio.sleep(0.4)

        for metric, (has_sum, unit, unit_class, label) in HISTORY_METRICS.items():
            if not rows[metric]:
                continue
            meta = StatisticMetaData(
                has_sum=has_sum,
                mean_type=(
                    StatisticMeanType.NONE if has_sum else StatisticMeanType.ARITHMETIC
                ),
                name=f"{name} · {label}",
                source="catlink",
                statistic_id=ids[metric],
                unit_of_measurement=unit,
                unit_class=unit_class,
            )
            async_add_external_statistics(hass, meta, rows[metric])
        _LOGGER.info("CatLink history: %s day(s) imported for %s", len(rows["idas"]), name)
