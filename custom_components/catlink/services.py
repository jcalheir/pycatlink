"""Read-only raw API access (fork addition).

``catlink.api_request`` performs an authenticated GET against the CatLink API
with the account already configured in Home Assistant and returns the JSON.
Only GET on ``token/...`` paths is allowed, so it cannot send device commands.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from pycatlink.const import HttpMethod

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

SERVICE_API_REQUEST = "api_request"

SCHEMA = vol.Schema(
    {
        vol.Required("path"): cv.string,
        vol.Optional("params", default={}): dict,
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""

    async def _api_request(call: ServiceCall) -> ServiceResponse:
        path: str = call.data["path"].lstrip("/")
        if not path.startswith("token/") or ".." in path:
            raise ServiceValidationError("path must start with 'token/'")
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]
        if not entries:
            raise ServiceValidationError("No loaded CatLink account")
        client = entries[0].runtime_data.account._client  # noqa: SLF001
        params: dict[str, Any] = {str(k): v for k, v in call.data["params"].items()}
        return await client.request_with_auto_login(
            path=path, method=HttpMethod.GET, parameters=params
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_API_REQUEST,
        _api_request,
        schema=SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
