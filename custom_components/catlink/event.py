"""Event platform for CatLink (fork addition): litter box visits."""

from __future__ import annotations

from pycatlink.c08 import CatlinkC08Device

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .models import CatlinkConfigEntry
from .visit_entities import CatlinkVisitEvent


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CatlinkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up visit events: one per cat and one for unidentified visits."""
    coordinator = entry.runtime_data.coordinator
    entities = [CatlinkVisitEvent(coordinator, pet_id) for pet_id in coordinator.data.pets]
    entities.extend(
        CatlinkVisitEvent(coordinator, None, device_id)
        for device_id, device in coordinator.data.devices.items()
        if isinstance(device, CatlinkC08Device)
    )
    async_add_entities(entities)
