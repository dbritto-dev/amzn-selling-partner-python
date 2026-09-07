import typing
from functools import cached_property

import httpx2

from ... import _base_client
from ..._path import path_template
from . import models

if typing.TYPE_CHECKING:
    from ..._client import Client

_RESOURCE_PATH = "vendor/orders/v1"


class Orders:
    def __init__(self, client: "Client") -> None:
        self._client = client

    def _get_purchase_orders_response(
        self, *, query: typing.Optional[models.GetPurchaseOrdersQuery] = None
    ) -> httpx2.Response:
        return self._client._request(
            _base_client.RequestOptions(
                method="GET",
                url=f"{_RESOURCE_PATH}/purchaseOrders",
                params=query.model_dump(exclude_none=True) if query is not None else None,
            )
        )

    def get_purchase_orders(
        self, *, query: typing.Optional[models.GetPurchaseOrdersQuery] = None
    ) -> typing.List[models.Order]:
        orders: typing.List[models.Order] = []
        current_query = query

        while True:
            response = self._get_purchase_orders_response(query=current_query)
            data = models.GetPurchaseOrdersResponse.model_validate_json(response.content)
            if data.payload is None or data.payload.orders is None:
                break

            orders.extend(data.payload.orders)

            next_token = (
                data.payload.pagination.nextToken if data.payload.pagination is not None else None
            )
            if next_token is None:
                break

            current_query = (
                current_query.model_copy()
                if current_query is not None
                else models.GetPurchaseOrdersQuery()
            )
            current_query.nextToken = next_token

        return orders

    def _get_purchase_order_response(self, purchase_order_number: str) -> httpx2.Response:
        return self._client._request(
            _base_client.RequestOptions(
                method="GET",
                url=path_template(
                    f"{_RESOURCE_PATH}/purchaseOrders/{{purchase_order_number}}",
                    purchase_order_number=purchase_order_number,
                ),
            )
        )

    def get_purchase_order(self, purchase_order_number: str) -> typing.Optional[models.Order]:
        if not purchase_order_number or not isinstance(purchase_order_number, str):
            raise ValueError(
                "purchase_order_number must be a string present but found "
                f"`{purchase_order_number}`"
            )

        response = self._get_purchase_order_response(purchase_order_number)
        data = models.GetPurchaseOrderResponse.model_validate_json(response.content)
        return data.payload

    @cached_property
    def with_raw_response(self) -> "OrdersWithRawResponse":
        return OrdersWithRawResponse(self)


class OrdersWithRawResponse:
    def __init__(self, orders: Orders) -> None:
        self._orders = orders

    def get_purchase_orders(
        self, *, query: typing.Optional[models.GetPurchaseOrdersQuery] = None
    ) -> httpx2.Response:
        return self._orders._get_purchase_orders_response(query=query)

    def get_purchase_order(self, purchase_order_number: str) -> httpx2.Response:
        return self._orders._get_purchase_order_response(purchase_order_number)
