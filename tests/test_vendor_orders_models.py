from decimal import Decimal

import amzn_selling_partner as sp


def test_vendor_order_models_match_sp_api_types() -> None:
    money = sp.vendor.orders.Money(
        currencyCode="USD",
        amount="12.34",
        unitOfMeasure=sp.vendor.orders.MoneyUnitOfMeasure.POUNDS,
    )
    quantity = sp.vendor.orders.ItemQuantity(unitOfMeasure=sp.vendor.orders.UnitOfMeasure.CASES)
    address = sp.vendor.orders.Address(
        name="Name",
        addressLine1="Street",
        countryCode="US",
        county="County",
        district="District",
    )

    assert money.amount == Decimal("12.34")
    assert money.unitOfMeasure == sp.vendor.orders.MoneyUnitOfMeasure.POUNDS
    assert quantity.unitOfMeasure == sp.vendor.orders.UnitOfMeasure.CASES
    assert address.county == "County"
    assert address.district == "District"


def test_vendor_acknowledgement_models_validate_current_values() -> None:
    acknowledgement = sp.vendor.orders.OrderAcknowledgement(
        purchaseOrderNumber="purchase-order",
        sellingParty=sp.vendor.orders.PartyIdentification(partyId="party-id"),
        acknowledgementDate="2026-09-02T00:00:00Z",
        items=[
            sp.vendor.orders.OrderAcknowledgementItem(
                orderedQuantity=sp.vendor.orders.ItemQuantity(amount=1),
                itemAcknowledgements=[
                    sp.vendor.orders.OrderItemAcknowledgement(
                        acknowledgementCode=sp.vendor.orders.AcknowledgementCode.ACCEPTED,
                        acknowledgedQuantity=sp.vendor.orders.ItemQuantity(amount=1),
                    )
                ],
            )
        ],
    )

    assert sp.vendor.orders.SubmitAcknowledgementRequest(
        acknowledgements=[acknowledgement]
    ).acknowledgements == [acknowledgement]


def test_vendor_order_status_models_validate_current_values() -> None:
    status = sp.vendor.orders.OrderStatus(
        purchaseOrderNumber="purchase-order",
        purchaseOrderStatus=sp.vendor.orders.PurchaseOrderStatus.OPEN,
        purchaseOrderDate="2026-09-02T00:00:00Z",
        sellingParty=sp.vendor.orders.PartyIdentification(partyId="seller"),
        shipToParty=sp.vendor.orders.PartyIdentification(partyId="warehouse"),
        itemStatus=[
            sp.vendor.orders.OrderItemStatus(
                itemSequenceNumber="1",
                acknowledgementStatus=sp.vendor.orders.AcknowledgementStatus(
                    confirmationStatus=sp.vendor.orders.ItemConfirmationStatus.ACCEPTED,
                ),
                receivingStatus=sp.vendor.orders.ReceivingStatus(
                    receiveStatus=sp.vendor.orders.ItemReceiveStatus.NOT_RECEIVED,
                ),
            )
        ],
    )

    assert sp.vendor.orders.GetPurchaseOrdersStatusResponse(
        payload=sp.vendor.orders.OrderListStatus(ordersStatus=[status])
    ).payload.ordersStatus == [status]
