"""describe: an upstream error for a log line, its repr, but never an aiohttp error's URL, headers or host."""

import errno

import aiohttp
import pytest
from aiohttp import RequestInfo
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from custom_components.deviceside.core.errors import describe, traceback_is_safe

# What aiohue sends, as an aiohttp error holds it: the bridge's address, a resource id and the app key.
URL_ = URL("https://192.0.2.1/clip/v2/resource/light/a-resource-id")
REQUEST = RequestInfo(URL_, "PUT", CIMultiDictProxy(CIMultiDict({"hue-application-key": "an-app-key"})), URL_)
CONNECTION = aiohttp.client_reqrep.ConnectionKey("192.0.2.1", 443, True, True, None, None, None)


@pytest.mark.parametrize(
    ("err", "described"),
    [
        pytest.param(
            aiohttp.ClientResponseError(REQUEST, (), status=500, message="Internal Server Error"),
            "ClientResponseError(status=500, message='Internal Server Error')",
            id="a_response_error",
        ),
        pytest.param(
            aiohttp.ClientConnectorError(CONNECTION, OSError(errno.ECONNREFUSED, "Connect call failed")),
            "ClientConnectorError('Connect call failed')",
            id="a_connection_error",
        ),
        pytest.param(aiohttp.InvalidURL(URL_), "InvalidURL()", id="another_client_error"),
        pytest.param(TimeoutError(), "TimeoutError()", id="any_other_error_is_its_repr"),
    ],
)
def test_an_error_is_described_without_what_addresses_the_device(err, described):
    assert describe(err) == described
    assert all(secret not in describe(err) for secret in ("192.0.2.1", "a-resource-id", "an-app-key"))


def test_only_an_aiohttp_errors_traceback_is_kept_out():
    assert not traceback_is_safe(aiohttp.ClientResponseError(REQUEST, (), status=500))
    assert traceback_is_safe(RuntimeError("bridge gone"))
