"""CatLink integration."""

import asyncio
from datetime import timedelta
import logging
from typing import Any

from . import email_login  # noqa: F401  (fork-only: email login shim)
from pycatlink.account import CatlinkAccount
from pycatlink.models import CatlinkAccountConfig

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from homeassistant.helpers.event import async_track_time_interval

from .services import async_setup_services
from .visits import async_sync_history

from .const import (
    CONF_BACKEND_URL,
    CONF_PASSWORD,
    CONF_PHONE,
    CONF_PHONE_INTERNATIONAL_CODE,
)
from .coordinator import CatlinkDataUpdateCoordinator
from .models import CatlinkConfigEntry, CatlinkData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up integration-wide services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CatlinkConfigEntry) -> bool:
    """Set up CatLink from a config entry."""
    phone = entry.data[CONF_PHONE]
    password = entry.data[CONF_PASSWORD]
    international_code = entry.data[CONF_PHONE_INTERNATIONAL_CODE]
    backend_url = entry.data[CONF_BACKEND_URL]

    config = CatlinkAccountConfig(
        phone=phone,
        password=password,
        phone_international_code=international_code,
        api_base=backend_url,
    )
    account = CatlinkAccount(config)

    coordinator = CatlinkDataUpdateCoordinator(hass, account, entry)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = CatlinkData(account=account, coordinator=coordinator)

    _LOGGER.info("Discovered %d CatLink device(s)", len(coordinator.data.devices))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    coordinator.async_update_listeners()

    sync_lock = asyncio.Lock()

    async def _sync_history(_now: Any = None) -> None:
        if sync_lock.locked():
            return
        try:
            async with sync_lock:
                await async_sync_history(hass, coordinator.visits, coordinator.data.pets)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("CatLink history sync failed")

    entry.async_create_background_task(hass, _sync_history(), "catlink_history_sync")
    entry.async_on_unload(
        async_track_time_interval(hass, _sync_history, timedelta(hours=1))
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: CatlinkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
