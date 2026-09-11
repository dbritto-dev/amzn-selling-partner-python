"""Regions, endpoints and marketplaces."""

from __future__ import annotations

import enum

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"


class Region(enum.Enum):
    NA = ("https://sellingpartnerapi-na.amazon.com", "https://sandbox.sellingpartnerapi-na.amazon.com", "us-east-1")
    EU = ("https://sellingpartnerapi-eu.amazon.com", "https://sandbox.sellingpartnerapi-eu.amazon.com", "eu-west-1")
    FE = ("https://sellingpartnerapi-fe.amazon.com", "https://sandbox.sellingpartnerapi-fe.amazon.com", "us-west-2")

    # aliases kept for the old ``SellingPartnerRegion`` names
    NORTH_AMERICA = NA
    EUROPE = EU
    FAR_EAST = FE

    @property
    def endpoint(self) -> str:
        return self.value[0]

    @property
    def sandbox_endpoint(self) -> str:
        return self.value[1]

    @property
    def aws_region(self) -> str:
        return self.value[2]

    # old property names
    api_endpoint = endpoint
    api_sandbox_endpoint = sandbox_endpoint

    @property
    def region_name(self) -> str:
        return self.aws_region

    def base_url(self, *, sandbox: bool = False) -> str:
        return self.sandbox_endpoint if sandbox else self.endpoint


class Marketplace(enum.StrEnum):
    """Marketplace identifiers (value) with their region and country code."""

    # North America
    CA = "A2EUQ1WTGCTBG2"
    US = "ATVPDKIKX0DER"
    MX = "A1AM78C64UM0Y8"
    BR = "A2Q3Y263D00KWC"
    # Europe
    IE = "A28R8C7NBKEWEA"
    ES = "A1RKKUPIHCS9HS"
    UK = "A1F83G8C2ARO7P"
    FR = "A13V1IB3VIYZZH"
    BE = "AMEN7PMS3EDWL"
    NL = "A1805IZSGTT6HS"
    DE = "A1PA6795UKMFR9"
    IT = "APJ6JRA9NG5V4"
    SE = "A2NODRKZP88ZB9"
    ZA = "AE08WJ6YKNBMC"
    PL = "A1C3SOZRARQ6R3"
    EG = "ARBP9OOSHTCHU"
    TR = "A33AVAJ2PDY3EV"
    SA = "A17E79C6D8DWNP"
    AE = "A2VIGQ35RCS4UG"
    IN = "A21TJRUUN4KGV"
    # Far East
    SG = "A19VAU5U5O7RUS"
    AU = "A39IBJ37TRP1C6"
    JP = "A1VC38T7YXB528"

    @property
    def region(self) -> Region:
        return _MARKETPLACE_REGION[self]

    @property
    def country_code(self) -> str:
        return self.name

    @classmethod
    def from_id(cls, marketplace_id: str) -> Marketplace:
        return cls(marketplace_id)


_MARKETPLACE_REGION: dict[Marketplace, Region] = {
    **{m: Region.NA for m in (Marketplace.CA, Marketplace.US, Marketplace.MX, Marketplace.BR)},
    **{
        m: Region.EU
        for m in (
            Marketplace.IE,
            Marketplace.ES,
            Marketplace.UK,
            Marketplace.FR,
            Marketplace.BE,
            Marketplace.NL,
            Marketplace.DE,
            Marketplace.IT,
            Marketplace.SE,
            Marketplace.ZA,
            Marketplace.PL,
            Marketplace.EG,
            Marketplace.TR,
            Marketplace.SA,
            Marketplace.AE,
            Marketplace.IN,
        )
    },
    **{m: Region.FE for m in (Marketplace.SG, Marketplace.AU, Marketplace.JP)},
}

__all__ = ["LWA_TOKEN_URL", "Marketplace", "Region"]
