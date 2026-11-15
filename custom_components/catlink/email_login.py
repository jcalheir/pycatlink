"""Fork-only shim: email login for the published pycatlink library.

Home Assistant installs pycatlink from PyPI (see manifest.json), which only
knows phone logins. Until a release with email support exists, add it here.
This is a no-op once the installed library already supports email logins.
"""

from typing import Any

from pycatlink import client as _client
from pycatlink.const import (
    DATA_KEY_TOKEN,
    PARAMETER_INTERNATIONAL_CODE,
    PARAMETER_MOBILE,
    PARAMETER_PASSWORD,
    PARAMETER_PLATFORM,
    PLATFORM_ANDROID,
    RESPONSE_KEY_DATA,
    HttpMethod,
)
from pycatlink.exceptions import CatlinkLoginError

API_LOGIN_EMAIL = "login/email"
API_LOGIN_PASSWORD = "login/password"
PARAMETER_EMAIL = "email"


def _login_request(self: Any) -> tuple[str, dict[str, Any]]:
    login = str(self.config.phone).strip()
    if "@" in login:
        return API_LOGIN_EMAIL, {
            PARAMETER_PLATFORM: PLATFORM_ANDROID,
            PARAMETER_EMAIL: login,
            PARAMETER_PASSWORD: self.password,
        }
    return API_LOGIN_PASSWORD, {
        PARAMETER_PLATFORM: PLATFORM_ANDROID,
        PARAMETER_INTERNATIONAL_CODE: self.config.phone_international_code,
        PARAMETER_MOBILE: login,
        PARAMETER_PASSWORD: self.password,
    }


async def _async_login(self: Any) -> None:
    path, parameters = self._login_request()
    response = await self.request(
        path=path, method=HttpMethod.POST, parameters=parameters
    )
    token = response.get(RESPONSE_KEY_DATA, {}).get(DATA_KEY_TOKEN)
    if not token:
        raise CatlinkLoginError(self.config.phone, response)
    self.config.token = token


def apply() -> None:
    """Patch the library client unless it already supports email logins."""
    cls = _client.CatlinkApiClient
    if hasattr(cls, "_login_request"):
        return
    cls._login_request = _login_request
    cls.async_login = _async_login


apply()
