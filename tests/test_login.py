from pycatlink.client import CatlinkApiClient
from pycatlink.const import API_LOGIN_EMAIL, API_LOGIN_PASSWORD
from pycatlink.models import CatlinkAccountConfig


def _client(login: str) -> CatlinkApiClient:
    return CatlinkApiClient(
        CatlinkAccountConfig(phone=login, password="secret", phone_international_code="351")
    )


def test_phone_login_uses_password_endpoint() -> None:
    path, params = _client("912345678")._login_request()
    assert path == API_LOGIN_PASSWORD
    assert params["mobile"] == "912345678"
    assert params["internationalCode"] == "351"
    assert "email" not in params


def test_email_login_uses_email_endpoint() -> None:
    path, params = _client(" user@example.com ")._login_request()
    assert path == API_LOGIN_EMAIL
    assert params["email"] == "user@example.com"
    assert "mobile" not in params and "internationalCode" not in params
    assert params["password"] != "secret"  # encrypted like phone logins
