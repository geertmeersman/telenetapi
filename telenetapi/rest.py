"""Telenet library."""
from __future__ import annotations

import logging
import urllib.parse

from requests import Session

from .const import BASE_HEADERS, DEFAULT_TELENET_ENVIRONMENT, TIMEOUT
from .exceptions import BadCredentialsException, TelenetServiceException
from .models import TelenetEnvironment

_LOGGER = logging.getLogger(__name__)


class TelenetClient:
    """Class to communicate with the Telenet API."""

    session: Session
    environment: TelenetEnvironment

    def __init__(
        self,
        username,
        password,
        headers: dict | None = BASE_HEADERS,
        environment: TelenetEnvironment = DEFAULT_TELENET_ENVIRONMENT,
    ) -> None:
        """Initialize the Communication API to get data."""
        self.username = username
        self.password = password
        self.environment = environment
        self.session = Session()
        self.session.headers = headers
        self.userdetails = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36",
            "Referer": "https://www2.telenet.be/residential/nl/mijn-telenet",
            "x-alt-referer": "https://www2.telenet.be/",
        }

    def request(self, url, data=None):
        """Send a request to Telenet."""
        if data is None:
            _LOGGER.debug(f"Calling GET {url}")
            response = self.session.get(url, timeout=TIMEOUT)
        else:
            _LOGGER.debug(f"Calling POST {url}")
            response = self.session.post(url, data, timeout=TIMEOUT)

        self.session.headers["X-TOKEN-XSRF"] = self.session.cookies.get("TOKEN-XSRF")
        return response

    def login(self) -> dict:
        """Start a new Telenet session with a user & password."""
        _LOGGER.debug("[TelenetClient|login|start]")
        response = self.request(f"{self.environment.ocapi_oauth}/userdetails")
        if response.status_code == 200:
            # Return if already authenticated
            return response.json()
        if response.status_code != 401 and response.status_code != 403:
            raise TelenetServiceException(
                f"HTTP {response.status_code} error while authenticating {response.url}"
            )

        """Fetch state & nonce"""
        tokens = response.text.split(",", maxsplit=2)
        if not tokens or len(tokens) != 2:
            raise TelenetServiceException(
                f"HTTP 401 not returning the tokens for {response.url}"
            )
        state, nonce = tokens

        """Login process"""
        response = self.request(
            f'{self.environment.openid}/oauth/authorize?client_id=ocapi&response_type=code&claims={{"id_token":{{"http://telenet.be/claims/roles":null,"http://telenet.be/claims/licenses":null}}}}&lang=nl&state={state}&nonce={nonce}&prompt=login',
        )
        if response.status_code != 200 or "openid/login" not in str(response.url):
            raise TelenetServiceException(response.text())
        response = self.request(
            f"{self.environment.openid}/login.do",
            {
                "j_username": self.username,
                "j_password": self.password,
                "rememberme": True,
            },
        )
        if "authentication_error" in response.url:
            raise BadCredentialsException(response.text)
        self.session.headers["X-TOKEN-XSRF"] = self.session.cookies.get("TOKEN-XSRF")

        response = self.request(
            f"{self.environment.ocapi_oauth}/userdetails",
        )
        userdetails = response.json()
        if "customer_number" not in userdetails:
            raise BadCredentialsException(
                f"HTTP {response.status_code} Missing customer number"
            )
        self.userdetails = userdetails
        if "scopes" in self.userdetails:
            del self.userdetails["scopes"]
        return response.json()

    def ocapi(self, service, method, version=1, params={}, return_response=False):
        """Call Telenet OCAPI."""
        params = urllib.parse.urlencode(params)
        response = self.request(
            f"{self.environment.ocapi_public_api}/{service}-service/v{version}/{method}?{params}",
        )
        if return_response is True:
            return response
        if response.status_code == 200:
            return response.json()
        return False

    def fetch_data(self):
        """Fetch all Telenet data."""
        response = self.ocapi(
            "product", "products", params={"status": "ACTIVE"}, return_response=True
        )
        if response.status_code == 200:
            return self.fetch_new_api_data()
        if response.status_code == 500:
            return self.fetch_old_api_data()
        return {}

    def fetch_old_api_data(self):
        """Fetch old Telenet API data."""
        data = {}
        data.update({"telenet_api": "OLD"})
        return data

    def fetch_new_api_data(self):
        """Fetch new Telenet API data."""
        data = {}
        data.update({"telenet_api": "NEW"})

        data.update({"customer": self.ocapi("customer", "customers")})

        """
        data.update({"producttypes_plan":       self.ocapi("product", "product-subscriptions", params={"producttypes":"PLAN"})})
        data.update({"producttypes_mobile":     self.ocapi("product", "product-subscriptions", params={"producttypes":"MOBILE"})})
        data.update({"domain_name":             self.ocapi("product", "product-subscriptions", params={"producttypes":"DOMAIN_NAME"})})
        data.update({"producttypes_internet":   self.ocapi("product", "product-subscriptions", params={"producttypes":"INTERNET"})})
        data.update({"devices_to_return":       self.ocapi("product", "product-subscriptions", params={"producttypes":"DEVICES_TO_RETURN"})})
        data.update({"products":                self.ocapi("product", "products", params={"status":"ACTIVE,ACTIVATION_IN_PROGRESS"})})
        data.update({"mailboxesandaliases":     self.ocapi("mailbox-mgmt", "mailboxesandaliases")})
        data.update({"appointments":            self.ocapi("customer", "appointments", params={"satus":"open"})})
        data.update({"simdetails":              self.ocapi("mobile", "simdetails", version=2)})
        data.update({"accounts":                self.ocapi("billing", "accounts", version=2)})
        """
        """
https://api.prd.telenet.be/ocapi/public/api/billing-service/v1/account/products/x429890/billcycle-details?producttype=internet&count=3
https://api.prd.telenet.be/ocapi/public/api/mobile-service/v3/mobilesubscriptions/0479392769/usages
https://api.prd.telenet.be/ocapi/public/api/contact-service/v1/contact/addresses/9150757954913752494

https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/internet/x429890/usage?fromDate=2023-05-18&toDate=2023-06-17
https://api.prd.telenet.be/ocapi/public/api/product-service/v1/products/x429890?producttype=internet
https://api.prd.telenet.be/ocapi/public/api/product-service/v1/product-subscriptions?producttypes=IHC_DEVICE&status=ACTIVE,ACTIVATION_IN_PROGRESS
https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems?productIdentifier=x429890
https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/network-topology/68:02:B8:77:A1:F2?withClients=true
https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/68:02:B8:77:A1:F2/wireless-settings?withmetadata=true&withwirelessservice=true&productidentifier=x429890
https://api.prd.telenet.be/ocapi/public/api/resource-service/v1/modems/68:02:B8:77:A1:F2/advance-settings
        """

        return data
