# Built-in packages
import enum
import typing

# Third-party packages
import pydantic


class PurchaseOrderType(str, enum.Enum):
    REGULAR_ORDER = "RegularOrder"
    CONSIGNED_ORDER = "ConsignedOrder"
    NEW_PRODUCT_INTRODUCTION = "NewProductIntroduction"
    RUSH_ORDER = "RushOrder"


class PurchaseOrderState(str, enum.Enum):
    NEW = "New"
    ACKNOWLEDGED = "Acknowledged"
    CLOSED = "Closed"


class UnitOfMeasure(str, enum.Enum):
    CASES = "Cases"
    EACHES = "Eaches"


class MethodOfPayment(str, enum.Enum):
    PAID_BY_BUYER = "PaidByBuyer"
    COLLECT_ON_DELIVERY = "CollectOnDelivery"
    DEFINED_BY_BUYER_AND_SELLER = "DefinedByBuyerAndSeller"
    FOB_PORT_OF_CALL = "FOBPortOfCall"
    PREPAID_BY_SELLER = "PrepaidBySeller"
    PAID_BY_SELLER = "PaidBySeller"


class InternationalCommercialTerms(str, enum.Enum):
    EX_WORKS = "ExWorks"
    FREE_CARRIER = "FreeCarrier"
    FREE_ON_BOARD = "FreeOnBoard"
    FREE_ALONG_SIDE_SHIP = "FreeAlongSideShip"
    CARRIAGE_PAID_TO = "CarriagePaidTo"
    COST_AND_FREIGHT = "CostAndFreight"
    CARRIAGE_AND_INSURANCE_PAID_TO = "CarriageAndInsurancePaidTo"
    COST_INSURANCE_AND_FREIGHT = "CostInsuranceAndFreight"
    DELIVERED_AT_TERMINAL = "DeliveredAtTerminal"
    DELIVERED_AT_PLACE = "DeliveredAtPlace"
    DELIVER_DUTY_PAID = "DeliverDutyPaid"


class TaxRegistrationType(str, enum.Enum):
    VALUE_ADDED_TAX = "VAT"
    GOODS_AND_SERVICES_TAX = "GST"


class PaymentMethod(str, enum.Enum):
    INVOICE = "Invoice"
    CONSIGNMENT = "Consignment"
    CREDIT_CARD = "CreditCard"
    PREPAID = "Prepaid"


class SortOrder(str, enum.Enum):
    ASCENDING = "ASC"
    DESCENDING = "DESC"


class PoItemState(enum.Enum):
    CANCELLED = "Cancelled"


DateTimeInterval = typing.NewType("DateTimeInterval", str)


class Money(pydantic.BaseModel):
    currencyCode: str
    amount: typing.Optional[float]


class ItemQuantity(pydantic.BaseModel):
    amount: typing.Optional[int]
    unitOfMeasure: typing.Optional[str]
    unitSize: typing.Optional[int]


class OrderItem(pydantic.BaseModel):
    itemSequenceNumber: str
    orderedQuantity: ItemQuantity
    isBackOrderAllowed: bool
    netCost: typing.Optional[Money]
    listPrice: typing.Optional[Money]
    amazonProductIdentifier: typing.Optional[str]
    vendorProductIdentifier: typing.Optional[str]


class ImportDetails(pydantic.BaseModel):
    methodOfPayment: typing.Optional[MethodOfPayment]
    internationalCommercialTerms: typing.Optional[InternationalCommercialTerms]
    portOfDelivery: typing.Optional[str]
    importContainers: typing.Optional[str]
    shippingInstructions: typing.Optional[str]


class Address(pydantic.BaseModel):
    name: str
    addressLine1: str
    countryCode: str
    addressLine2: typing.Optional[str]
    addressLine3: typing.Optional[str]
    city: typing.Optional[str]
    country: typing.Optional[str]
    stateOrRegion: typing.Optional[str]
    postalCode: typing.Optional[str]
    phone: typing.Optional[str]


class TaxRegistrationDetails(pydantic.BaseModel):
    taxRegistrationType: TaxRegistrationType
    taxRegistrationNumber: str


class PartyIdentification(pydantic.BaseModel):
    partyId: str
    address: typing.Optional[Address]
    taxInfo: typing.Optional[TaxRegistrationDetails]


class OrderDetails(pydantic.BaseModel):
    purchaseOrderDate: str
    purchaseOrderStateChangedDate: str
    purchaseOrderType: PurchaseOrderType
    items: typing.List[OrderItem]
    purchaseOrderChangedDate: typing.Optional[str]
    importDetails: typing.Optional[ImportDetails]
    dealCode: typing.Optional[str]
    paymentMethod: typing.Optional[PaymentMethod]
    buyingParty: typing.Optional[PartyIdentification]
    sellingParty: typing.Optional[PartyIdentification]
    shipToParty: typing.Optional[PartyIdentification]
    billToParty: typing.Optional[PartyIdentification]
    shipWindow: typing.Optional[DateTimeInterval]
    deliveryWindow: typing.Optional[DateTimeInterval]


class Order(pydantic.BaseModel):
    purchaseOrderNumber: str
    purchaseOrderState: PurchaseOrderState
    orderDetails: typing.Optional[OrderDetails]


class Pagination(pydantic.BaseModel):
    nextToken: typing.Optional[str]


class OrderList(pydantic.BaseModel):
    pagination: typing.Optional[Pagination]
    orders: typing.Optional[typing.List[Order]]


class TransactionId(pydantic.BaseModel):
    transactionId: typing.Optional[str]


class Error(pydantic.BaseModel):
    code: str
    message: str
    details: typing.Optional[str]


class GetPurchaseOrdersResponse(pydantic.BaseModel):
    payload: typing.Optional[OrderList]
    errors: typing.Optional[typing.List[Error]]


class GetPurchaseOrdersQuery(pydantic.BaseModel):
    limit: typing.Optional[int]
    createdAfter: typing.Optional[str]
    createdBefore: typing.Optional[str]
    sortOrder: typing.Optional[SortOrder]
    nextToken: typing.Optional[str]
    includeDetails: typing.Optional[bool]
    changedAfter: typing.Optional[str]
    changedBefore: typing.Optional[str]
    poItemState: typing.Optional[PoItemState]
    isPOChanged: typing.Optional[bool]
    purchaseOrderState: typing.Optional[PurchaseOrderState]
    orderingVendorCode: typing.Optional[str]


class GetPurchaseOrderResponse(pydantic.BaseModel):
    payload: typing.Optional[Order]
    errors: typing.Optional[typing.List[Error]]
