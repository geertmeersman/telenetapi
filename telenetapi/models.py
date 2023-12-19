"""Models used by telenetapi."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TelenetEnvironment:
    """Class to describe a Telenet environment."""

    ocapi: str
    ocapi_public: str
    ocapi_public_api: str
    ocapi_oauth: str
    openid: str
    referer: str
    x_alt_referer: str

@dataclass
class TelenetDataElement:
    """Class to describe a Telenet API response."""

    key: str
    account: str
    plan: str
    data: str
