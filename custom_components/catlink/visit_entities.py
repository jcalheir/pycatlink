"""Fork addition: entities for litter box visits (events and per-cat sensors)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER
from .coordinator import CatlinkDataUpdateCoordinator
from .visits import KINDS, DaySummary, Visit


def pet_device_info(coordinator: CatlinkDataUpdateCoordinator, pet_id: str) -> DeviceInfo:
    """Same device as the upstream pet sensors."""
    pet = coordinator.data.pets[pet_id]
    return DeviceInfo(
        identifiers={(DOMAIN, f"pet_{pet_id}")},
        name=pet.pet_name or f"Pet {pet_id}",
        manufacturer=MANUFACTURER,
        model="Pet",
    )


class CatlinkVisitEvent(CoordinatorEntity[CatlinkDataUpdateCoordinator], EventEntity):
    """Fires when a cat (or an unidentified cat) uses the litter box."""

    _attr_has_entity_name = True
    _attr_event_types = KINDS
    _attr_icon = "mdi:cat"

    def __init__(
        self,
        coordinator: CatlinkDataUpdateCoordinator,
        pet_id: str | None,
        device_id: str | None = None,
    ) -> None:
        """Initialize. pet_id None = unidentified visits on the litter box device."""
        super().__init__(coordinator)
        self._pet_id = pet_id
        if pet_id:
            self._attr_name = "Ida à caixa"
            self._attr_unique_id = f"pet_{pet_id}_visit_event"
            self._attr_device_info = pet_device_info(coordinator, pet_id)
        else:
            self._attr_name = "Ida não identificada"
            self._attr_unique_id = f"{device_id}_unidentified_visit_event"
            self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, str(device_id))})

    @callback
    def _handle_coordinator_update(self) -> None:
        state = self.coordinator.data.visits
        if state is not None:
            for visit in state.new_visits:
                if visit.pet_id == self._pet_id:
                    self._trigger_event(visit.kind, visit.attributes())
                    self.async_write_ha_state()
        super()._handle_coordinator_update()


class CatlinkLastVisitSensor(
    CoordinatorEntity[CatlinkDataUpdateCoordinator], SensorEntity, RestoreEntity
):
    """Timestamp of the last visit, with type, weight and duration."""

    _attr_has_entity_name = True
    _attr_name = "Última ida"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, coordinator: CatlinkDataUpdateCoordinator, pet_id: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._pet_id = pet_id
        self._attr_unique_id = f"pet_{pet_id}_last_visit"
        self._attr_device_info = pet_device_info(coordinator, pet_id)
        self._restored: tuple[datetime, dict[str, Any]] | None = None

    async def async_added_to_hass(self) -> None:
        """Restore the last known visit after a restart."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state not in (
            "unknown",
            "unavailable",
        ):
            when = dt_util.parse_datetime(last.state)
            if when:
                self._restored = (when, dict(last.attributes))

    def _visit(self) -> Visit | None:
        state = self.coordinator.data.visits
        return state.last_visit.get(self._pet_id) if state else None

    @property
    def native_value(self) -> datetime | None:
        """Return the time of the last visit."""
        visit = self._visit()
        if visit and (not self._restored or visit.when >= self._restored[0]):
            return visit.when
        return self._restored[0] if self._restored else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Type, weight and duration of the last visit."""
        visit = self._visit()
        if visit and (not self._restored or visit.when >= self._restored[0]):
            return {k: v for k, v in visit.attributes().items() if k != "hora"}
        if self._restored:
            keep = ("tipo", "peso_kg", "duracao_s")
            return {k: v for k, v in self._restored[1].items() if k in keep}
        return None


@dataclass(frozen=True, kw_only=True)
class TodayDescription(SensorEntityDescription):
    """Describes a 'today' sensor."""

    value_fn: Callable[[DaySummary], Any]


TODAY_SENSORS: tuple[TodayDescription, ...] = (
    TodayDescription(key="visits_today", name="Idas hoje", icon="mdi:counter",
                     value_fn=lambda s: s.visits),
    TodayDescription(key="pee_today", name="Xixi hoje", icon="mdi:water",
                     value_fn=lambda s: s.pee),
    TodayDescription(key="poop_today", name="Cocó hoje", icon="mdi:emoticon-poop",
                     value_fn=lambda s: s.poop),
    TodayDescription(key="duration_today", name="Duração média hoje",
                     device_class=SensorDeviceClass.DURATION,
                     native_unit_of_measurement=UnitOfTime.SECONDS, icon="mdi:timer-outline",
                     value_fn=lambda s: s.duration_avg_s),
    TodayDescription(key="weight_today", name="Peso médio hoje",
                     device_class=SensorDeviceClass.WEIGHT,
                     native_unit_of_measurement=UnitOfMass.KILOGRAMS,
                     suggested_display_precision=2,
                     value_fn=lambda s: s.weight_avg_kg),
    TodayDescription(key="health_today", name="Estado hoje", icon="mdi:heart-pulse",
                     value_fn=lambda s: (s.health_status or "").lower() or None),
)


class CatlinkTodaySensor(CoordinatorEntity[CatlinkDataUpdateCoordinator], SensorEntity):
    """Today's toilet summary for one cat (same numbers as the app)."""

    _attr_has_entity_name = True
    entity_description: TodayDescription

    def __init__(
        self,
        coordinator: CatlinkDataUpdateCoordinator,
        pet_id: str,
        description: TodayDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self.entity_description = description
        self._pet_id = pet_id
        self._attr_unique_id = f"pet_{pet_id}_{description.key}"
        self._attr_device_info = pet_device_info(coordinator, pet_id)

    @property
    def native_value(self) -> Any:
        """Return today's value."""
        state = self.coordinator.data.visits
        summary = state.today.get(self._pet_id) if state else None
        return self.entity_description.value_fn(summary) if summary else None


def visit_sensors(coordinator: CatlinkDataUpdateCoordinator) -> list[SensorEntity]:
    """All fork sensors."""
    entities: list[SensorEntity] = []
    for pet_id in coordinator.data.pets:
        entities.append(CatlinkLastVisitSensor(coordinator, pet_id))
        entities.extend(
            CatlinkTodaySensor(coordinator, pet_id, d) for d in TODAY_SENSORS
        )
    return entities
