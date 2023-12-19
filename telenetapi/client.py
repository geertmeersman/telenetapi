"""Telenet library."""
from __future__ import annotations

from datetime import datetime
import logging
import urllib.parse

from requests import Session

from .const import (
    BASE_HEADERS,
    DEFAULT_LANGUAGE,
    DEFAULT_TELENET_ENVIRONMENT,
    LANGUAGES,
    TIMEOUT,
)
from .exceptions import BadCredentialsException, TelenetServiceException
from .models import TelenetEnvironment
from .utils import kb_to_gb, str_to_float

_LOGGER = logging.getLogger(__name__)


class TelenetClient:
    """Class to communicate with the Telenet API."""

    session: Session
    environment: TelenetEnvironment

    def __init__(
        self,
        username,
        password,
        language: str | None = DEFAULT_LANGUAGE,
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
        self.bss_system = None
        self.scopes = None
        self.product_specs = {}
        self.data = {"products": {}, "devices": {}, "bills": {}}
        self.language = language if language in LANGUAGES else DEFAULT_LANGUAGE

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
        if "scopes" in userdetails:
            self.scopes = userdetails["scopes"]
            del self.userdetails["scopes"]
        return response.json()

    def ocapi(self, service, method=None, version=1, params={}, return_response=False):
        """Call Telenet OCAPI."""
        params = urllib.parse.urlencode(params)
        if self.bss_system == "TELENET_LEGACY":
            for scope in service.split(","):
                if scope not in self.scopes:
                    _LOGGER.error(f"Service {service} is not available in your scopes")
                    return False
            response = self.request(
                f"{self.environment.ocapi_public}/?p={service}",
            )
        elif self.bss_system == "NETCRACKER":
            response = self.request(
                f"{self.environment.ocapi_public_api}/{service}-service/v{version}/{method}?{params}",
            )
        if return_response is True:
            return response
        if response.status_code == 200:
            return response.json()
        return False

    def get_data(self):
        """Fetch all Telenet data."""
        self.bss_system = self.userdetails.get("bss_system")
        self.data.update({"telenet_system": self.bss_system})
        self.data.update({"userdetails": self.userdetails})
        if self.bss_system == "TELENET_LEGACY":
            self.get_telenet_legacy()
        elif self.bss_system == "NETCRACKER":
            self.get_netcracker()

    #            self.data.update({"customer":  self.ocapi("customer", "customers")})

    def get_product_specs(self, specurl, is_child):
        """Fetch product specs data."""
        # print(f"SPECURL: {specurl}")
        parsed = urllib.parse.urlparse(specurl)
        product = parsed.path.split("/")[-1]

        if product not in self.product_specs:
            response = self.request(specurl)
            if response.status_code == 200:
                product_specs = response.json()
                self.product_specs.update({product: product_specs})
        else:
            product_specs = self.product_specs.get(product)
        product = product_specs.get("product")
        specs = {}
        if "service_category_limit" in product.get("characteristics"):
            specs.update(
                {
                    "included_volume": product.get("characteristics").get(
                        "service_category_limit"
                    )
                }
            )
        specs.update({"producttype": product.get("producttype")})
        if not is_child:
            specs.update({"price": self.get_product_price(product)})
            specs.update({"priceType": product.get("priceType")})
        for lc in product.get("localizedcontent"):
            if lc.get("locale") == self.language:
                specs.update({"name": lc.get("name")})
                continue
        return specs

    def get_product_price(self, product):
        """Retrieve product price."""
        if "characteristics" in product and "salespricevatincl" in product.get(
            "characteristics"
        ):
            return product.get("characteristics").get("salespricevatincl")
        return False

    def get_legacy_internet(self, product, specs):
        """Retrieve internet details."""
        response = self.ocapi("internetusage,modemdetails,modems")
        businessidentifier = None
        if response:
            for internetusage in response.get("internetusage"):
                businessidentifier = internetusage.get("businessidentifier")
                last_updated = internetusage.get("lastupdated")
                availableperiod = internetusage.get("availableperiods")[0]
                usage = availableperiod.get("usages")[0]
                includedvolume = 0
                if "included_volume" in specs:
                    includedvolume = int(specs.get("included_volume").get("value"))
                elif "includedvolume" in usage:
                    includedvolume = kb_to_gb(
                        usage.get("includedvolume")
                        + usage.get("extendedvolume").get("volume")
                    )
                totalusage = usage.get("totalusage")

                total_usage_with_offpeak = kb_to_gb(
                    totalusage.get("offpeak") + totalusage.get("wifree")
                )
                usage_pct = round(100 * total_usage_with_offpeak / includedvolume, 1)
                period_start = datetime.strptime(
                    usage.get("periodstart"), "%Y-%m-%dT%H:%M:%S.0%z"
                )
                period_end = datetime.strptime(
                    usage.get("periodend"), "%Y-%m-%dT%H:%M:%S.0%z"
                )
                period_length = period_end - period_start
                period_length_days = period_length.days
                period_length_seconds = period_length.total_seconds()
                period_used = datetime.now(period_start.tzinfo) - period_start
                period_used_seconds = period_used.total_seconds()
                period_used_percentage = round(
                    100 * period_used_seconds / period_length_seconds, 1
                )
                if period_used_percentage > 100:
                    period_used_percentage = 100

                daily_peak = []
                daily_off_peak = []
                daily_date = []
                dailyusages = usage.get("totalusage").get("dailyusages")
                if len(dailyusages) != 0:
                    for day in dailyusages:
                        if "peak" in day:
                            daily_peak.append(kb_to_gb(day.get("peak")))
                            daily_off_peak.append(kb_to_gb(day.get("offpeak")))
                        daily_date.append(day.get("date"))

                self.data.get("products").update(
                    {
                        businessidentifier: {
                            "last_updated": last_updated,
                            "periodstart": usage.get("periodstart"),
                            "periodend": usage.get("periodend"),
                            "included_volume": includedvolume,
                            "peak_usage": kb_to_gb(totalusage.get("peak")),
                            "wifree_usage": kb_to_gb(totalusage.get("wifree")),
                            "offpeak_usage": kb_to_gb(totalusage.get("offpeak")),
                            "total_usage_with_offpeak": kb_to_gb(
                                totalusage.get("peak") + totalusage.get("offpeak")
                            ),
                            "squeezed": usage.get("squeezed"),
                            "period_used_percentage": period_used_percentage,
                            "usage_pct": usage_pct,
                            "period_length_days": period_length_days,
                            "daily_peak": daily_peak,
                            "daily_off_peak": daily_off_peak,
                            "daily_date": daily_date,
                        }
                    }
                )
            if "modemdetails" in response:
                for modem in response.get("modemdetails"):
                    if modem.get("internetlineidentifier") == businessidentifier:
                        del modem["installationaddress"]
                        modem.update({"type": "Modem"})
                        self.data.get("devices").update(
                            {modem.get("cableroutername"): modem}
                        )
            if "modems" in response:
                for modem in response.get("modems"):
                    if modem.get("internetlineidentifier") == businessidentifier:
                        del modem["address"]
                        settings = modem.get("settings")
                        if len(settings) and settings[0].get("passphrase"):
                            passphrase = (
                                settings[0].get("passphrase").replace(":", r"\:")
                            )
                            modem.update(
                                {
                                    "passphrase": f"WIFI:S:{settings[0].get('ssid')};T:WPA;P:{passphrase};;"
                                }
                            )
                        modem.update({"type": "Wifi modem"})
                        self.data.get("devices").update({modem.get("hardware"): modem})

    def get_legacy_tv(self, product):
        """Retrieve internet details."""
        data = {}
        mapping = [
            "identifier",
            "customerproductid",
            "accountnumber",
            "label",
            "rateclassdescription",
        ]
        for key in mapping:
            data.update({key: product.get(key)})
        response = self.ocapi("digitaltvdetails,digitaltvunbilledusage")
        if response:
            for digitaltvdetails in response.get("digitaltvdetails"):
                for device in digitaltvdetails.get("devices"):
                    self.data.get("devices").update(
                        {device.get("serialnumber"): device}
                    )
            open_bill = 0
            for digitaltvunbilledusage in response.get("digitaltvunbilledusage"):
                for key in digitaltvunbilledusage:
                    if "usage" in key and "total" in digitaltvunbilledusage.get(key):
                        open_bill += str_to_float(
                            digitaltvunbilledusage.get(key).get("total")
                        )
            self.data.get("bills").update(
                {
                    "dtv": {
                        "total": open_bill,
                        "unit": "EURO",
                        "data": digitaltvunbilledusage,
                    }
                }
            )

        return data

    def get_product(self, product, is_child=False):
        """Get product structure."""
        if (
            "productType" in product
            and product.get("productType") == "bundle"
            and len(product.get("children"))
        ):
            for child in product.get("children"):
                self.get_product(child, is_child=True)

        specs = self.get_product_specs(product.get("specurl"), is_child)
        _LOGGER.debug(
            f"{product.get('identifier')}|{product.get('productType')}|{product.get('label')}"
        )
        if self.bss_system == "TELENET_LEGACY":
            type = product.get("label").split(".")[0]
            _LOGGER.debug(f"TYPE: {type}")
            if type == "internet":
                self.get_legacy_internet(product, specs)
            elif type == "tv":
                self.get_legacy_tv(product)
        else:
            self.data.get("products").update(
                {
                    product.get("identifier"): {
                        #                    'productType': product.get('productType'),
                        "specs": specs
                    }
                }
            )

    def get_netcracker(self):
        """Fetch new Telenet API data."""
        products = self.ocapi(
            "product", "products", params={"status": "ACTIVE,ACTIVATION_IN_PROGRESS"}
        )
        for product in products:
            self.get_product(product)

        # self.data.update({"products":  products})
        _LOGGER.debug("--------------------------------------------------\n")

        """
        data.update({"producttypes_plan":       self.ocapi("product", "product-subscriptions", params={"producttypes":"PLAN"})})
        data.update({"producttypes_mobile":     self.ocapi("product", "product-subscriptions", params={"producttypes":"MOBILE"})})
        data.update({"domain_name":             self.ocapi("product", "product-subscriptions", params={"producttypes":"DOMAIN_NAME"})})
        data.update({"producttypes_internet":   self.ocapi("product", "product-subscriptions", params={"producttypes":"INTERNET"})})
        data.update({"devices_to_return":       self.ocapi("product", "product-subscriptions", params={"producttypes":"DEVICES_TO_RETURN"})})
        data.update({"mailboxesandaliases":     self.ocapi("mailbox-mgmt", "mailboxesandaliases")})
        data.update({"appointments":            self.ocapi("customer", "appointments", params={"satus":"open"})})
        data.update({"simdetails":              self.ocapi("mobile", "simdetails", version=2)})
        data.update({"accounts":                self.ocapi("billing", "accounts", version=2)})
        """

    def get_telenet_legacy(self):
        """Fetch old Telenet API data."""
        self.data.update({"contactdetails": self.ocapi("contactdetails")})
        response = self.ocapi("accounts")
        for account in response.get("accounts"):
            self.data.update({"account": account})
        """
            if 'products' in account and len(account.get('products')):
                products = account.get('products')
                for product in products:
                    product_list = products.get(product)
                    if len(product_list):
                        for product in product_list:
                            print(f"Type: {product.get('type')}")
                            print(f"businessidentifier: {product.get('businessidentifier')}")
        """
        response = self.ocapi("bills")
        if response:
            amount = 0
            bills = []
            for bills_array in response.get("bills"):
                for bill in bills_array.get("bills"):
                    if not bill.get("paid"):
                        amount += bill.get("billamount").get("amount")
                        bills.append(bill)
            self.data.get("bills").update(
                {"invoices": {"unpaid": amount, "unit": "EURO", "data": bills}}
            )

        response = self.ocapi("customerproductholding")
        for product in response.get("customerproductholding"):
            self.get_product(product)
            # print(product.get('identifier'))
