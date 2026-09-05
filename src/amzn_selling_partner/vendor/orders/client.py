import typing

from ... import client
from . import models


class Client(client.BaseClient):
    def get_resource_path(self) -> str:
        return "vendor/orders/v1"

    def _get_purchase_orders_response(
        self, *, query: typing.Optional[models.GetPurchaseOrdersQuery] = None
    ) -> models.GetPurchaseOrdersResponse:
        _response = self.http_session.get(
            self.get_operation_endpoint("purchaseOrders"),
            params=query and query.dict(exclude_none=True),
        )
        _response.raise_for_status()
        return models.GetPurchaseOrdersResponse(**_response.json())

    def get_purchase_orders(
        self, *, query: typing.Optional[models.GetPurchaseOrdersQuery] = None
    ) -> typing.List[models.Order]:
        data = self._get_purchase_orders_response(query=query)
        if data.payload is None or data.payload.orders is None:
            return []

        next_token = (
            data.payload.pagination.nextToken if data.payload.pagination is not None else None
        )

        if next_token is None:
            return data.payload.orders

        _query = query.copy() if query is not None else models.GetPurchaseOrdersQuery()
        _query.nextToken = next_token

        return data.payload.orders + self.get_purchase_orders(query=_query)

    def _get_purchase_order_response(
        self, purchase_order_number: str
    ) -> models.GetPurchaseOrderResponse:
        _response = self.http_session.get(
            self.get_operation_endpoint(f"purchaseOrders/{purchase_order_number}")
        )
        _response.raise_for_status()
        return models.GetPurchaseOrderResponse(**_response.json())

    def get_purchase_order(self, purchase_order_number: str) -> typing.Optional[models.Order]:
        if not purchase_order_number or not isinstance(purchase_order_number, str):
            raise ValueError(
                "purchase_order_number must be a string present but found "
                f"`{purchase_order_number}`"
            )

        data = self._get_purchase_order_response(purchase_order_number)
        return data.payload
