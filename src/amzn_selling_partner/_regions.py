import enum

__all__ = ["SellingPartnerRegion"]


class SellingPartnerRegion(tuple, enum.Enum):
    NORTH_AMERICA = (
        "https://sellingpartnerapi-na.amazon.com",
        "https://sandbox.sellingpartnerapi-na.amazon.com",
        "us-east-1",
    )
    EUROPE = (
        "https://sellingpartnerapi-eu.amazon.com",
        "https://sandbox.sellingpartnerapi-eu.amazon.com",
        "eu-west-1",
    )
    FAR_EAST = (
        "https://sellingpartnerapi-fe.amazon.com",
        "https://sandbox.sellingpartnerapi-fe.amazon.com",
        "us-west-2",
    )

    @property
    def api_endpoint(self) -> str:
        return self.value[0]

    @property
    def api_sandbox_endpoint(self) -> str:
        return self.value[1]

    @property
    def region_name(self) -> str:
        return self.value[2]
