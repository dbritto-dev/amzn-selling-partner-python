# Built-in packages
import enum
import typing
from decimal import Decimal

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


class MoneyUnitOfMeasure(str, enum.Enum):
    POUNDS = "POUNDS"
    OUNCES = "OUNCES"
    GRAMS = "GRAMS"
    KILOGRAMS = "KILOGRAMS"


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


class PoItemState(str, enum.Enum):
    CANCELLED = "Cancelled"


class AcknowledgementCode(str, enum.Enum):
    ACCEPTED = "Accepted"
    BACKORDERED = "Backordered"
    REJECTED = "Rejected"


class RejectionReason(str, enum.Enum):
    TEMPORARILY_UNAVAILABLE = "TemporarilyUnavailable"
    INVALID_PRODUCT_IDENTIFIER = "InvalidProductIdentifier"
    OBSOLETE_PRODUCT = "ObsoleteProduct"


class PurchaseOrderStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ItemConfirmationStatus(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"
    UNCONFIRMED = "UNCONFIRMED"


class ItemReceiveStatus(str, enum.Enum):
    NOT_RECEIVED = "NOT_RECEIVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"


DateTimeInterval = typing.NewType("DateTimeInterval", str)


class Money(pydantic.BaseModel):
    currencyCode: typing.Optional[str] = None
    amount: typing.Optional[Decimal] = None
    unitOfMeasure: typing.Optional[MoneyUnitOfMeasure] = None


class ItemQuantity(pydantic.BaseModel):
    amount: typing.Optional[int] = None
    unitOfMeasure: typing.Optional[UnitOfMeasure] = None
    unitSize: typing.Optional[int] = None


class OrderItem(pydantic.BaseModel):
    itemSequenceNumber: str
    orderedQuantity: ItemQuantity
    isBackOrderAllowed: bool
    netCost: typing.Optional[Money] = None
    listPrice: typing.Optional[Money] = None
    amazonProductIdentifier: typing.Optional[str] = None
    vendorProductIdentifier: typing.Optional[str] = None


class ImportDetails(pydantic.BaseModel):
    methodOfPayment: typing.Optional[MethodOfPayment] = None
    internationalCommercialTerms: typing.Optional[InternationalCommercialTerms] = None
    portOfDelivery: typing.Optional[str] = None
    importContainers: typing.Optional[str] = None
    shippingInstructions: typing.Optional[str] = None


class Address(pydantic.BaseModel):
    name: str
    addressLine1: str
    countryCode: str
    addressLine2: typing.Optional[str] = None
    addressLine3: typing.Optional[str] = None
    city: typing.Optional[str] = None
    country: typing.Optional[str] = None
    county: typing.Optional[str] = None
    district: typing.Optional[str] = None
    stateOrRegion: typing.Optional[str] = None
    postalCode: typing.Optional[str] = None
    phone: typing.Optional[str] = None


class TaxRegistrationDetails(pydantic.BaseModel):
    taxRegistrationType: TaxRegistrationType
    taxRegistrationNumber: str


class PartyIdentification(pydantic.BaseModel):
    partyId: str
    address: typing.Optional[Address] = None
    taxInfo: typing.Optional[TaxRegistrationDetails] = None


class OrderDetails(pydantic.BaseModel):
    purchaseOrderDate: str
    purchaseOrderStateChangedDate: str
    items: typing.List[OrderItem]
    purchaseOrderType: typing.Optional[PurchaseOrderType] = None
    purchaseOrderChangedDate: typing.Optional[str] = None
    importDetails: typing.Optional[ImportDetails] = None
    dealCode: typing.Optional[str] = None
    paymentMethod: typing.Optional[PaymentMethod] = None
    buyingParty: typing.Optional[PartyIdentification] = None
    sellingParty: typing.Optional[PartyIdentification] = None
    shipToParty: typing.Optional[PartyIdentification] = None
    billToParty: typing.Optional[PartyIdentification] = None
    shipWindow: typing.Optional[DateTimeInterval] = None
    deliveryWindow: typing.Optional[DateTimeInterval] = None


class Order(pydantic.BaseModel):
    purchaseOrderNumber: str
    purchaseOrderState: PurchaseOrderState
    orderDetails: typing.Optional[OrderDetails] = None


class Pagination(pydantic.BaseModel):
    nextToken: typing.Optional[str] = None


class OrderList(pydantic.BaseModel):
    pagination: typing.Optional[Pagination] = None
    orders: typing.Optional[typing.List[Order]] = None


class TransactionId(pydantic.BaseModel):
    transactionId: typing.Optional[str] = None


class Error(pydantic.BaseModel):
    code: str
    message: str
    details: typing.Optional[str] = None


class GetPurchaseOrdersResponse(pydantic.BaseModel):
    payload: typing.Optional[OrderList] = None
    errors: typing.Optional[typing.List[Error]] = None


class GetPurchaseOrdersQuery(pydantic.BaseModel):
    limit: typing.Optional[int] = None
    createdAfter: typing.Optional[str] = None
    createdBefore: typing.Optional[str] = None
    sortOrder: typing.Optional[SortOrder] = None
    nextToken: typing.Optional[str] = None
    includeDetails: typing.Optional[bool] = None
    changedAfter: typing.Optional[str] = None
    changedBefore: typing.Optional[str] = None
    poItemState: typing.Optional[PoItemState] = None
    isPOChanged: typing.Optional[bool] = None
    purchaseOrderState: typing.Optional[PurchaseOrderState] = None
    orderingVendorCode: typing.Optional[str] = None


class GetPurchaseOrderResponse(pydantic.BaseModel):
    payload: typing.Optional[Order] = None
    errors: typing.Optional[typing.List[Error]] = None


class OrderItemAcknowledgement(pydantic.BaseModel):
    acknowledgementCode: AcknowledgementCode
    acknowledgedQuantity: ItemQuantity
    scheduledShipDate: typing.Optional[str] = None
    scheduledDeliveryDate: typing.Optional[str] = None
    rejectionReason: typing.Optional[RejectionReason] = None


class OrderAcknowledgementItem(pydantic.BaseModel):
    orderedQuantity: ItemQuantity
    itemAcknowledgements: typing.List[OrderItemAcknowledgement]
    itemSequenceNumber: typing.Optional[str] = None
    amazonProductIdentifier: typing.Optional[str] = None
    vendorProductIdentifier: typing.Optional[str] = None
    netCost: typing.Optional[Money] = None
    listPrice: typing.Optional[Money] = None
    discountMultiplier: typing.Optional[str] = None


class OrderAcknowledgement(pydantic.BaseModel):
    purchaseOrderNumber: str
    sellingParty: PartyIdentification
    acknowledgementDate: str
    items: typing.List[OrderAcknowledgementItem]


class SubmitAcknowledgementRequest(pydantic.BaseModel):
    acknowledgements: typing.Optional[typing.List[OrderAcknowledgement]] = None


class SubmitAcknowledgementResponse(pydantic.BaseModel):
    payload: typing.Optional[TransactionId] = None
    errors: typing.Optional[typing.List[Error]] = None


class OrderedQuantityDetails(pydantic.BaseModel):
    updatedDate: typing.Optional[str] = None
    orderedQuantity: typing.Optional[ItemQuantity] = None
    cancelledQuantity: typing.Optional[ItemQuantity] = None


class OrderedQuantityStatus(pydantic.BaseModel):
    orderedQuantity: typing.Optional[ItemQuantity] = None
    orderedQuantityDetails: typing.Optional[typing.List[OrderedQuantityDetails]] = None


class AcknowledgementStatusDetails(pydantic.BaseModel):
    acknowledgementDate: typing.Optional[str] = None
    acceptedQuantity: typing.Optional[ItemQuantity] = None
    rejectedQuantity: typing.Optional[ItemQuantity] = None


class AcknowledgementStatus(pydantic.BaseModel):
    confirmationStatus: typing.Optional[ItemConfirmationStatus] = None
    acceptedQuantity: typing.Optional[ItemQuantity] = None
    rejectedQuantity: typing.Optional[ItemQuantity] = None
    acknowledgementStatusDetails: typing.Optional[typing.List[AcknowledgementStatusDetails]] = None


class ReceivingStatus(pydantic.BaseModel):
    receiveStatus: typing.Optional[ItemReceiveStatus] = None
    receivedQuantity: typing.Optional[ItemQuantity] = None
    lastReceiveDate: typing.Optional[str] = None


class OrderItemStatus(pydantic.BaseModel):
    itemSequenceNumber: str
    buyerProductIdentifier: typing.Optional[str] = None
    vendorProductIdentifier: typing.Optional[str] = None
    netCost: typing.Optional[Money] = None
    listPrice: typing.Optional[Money] = None
    orderedQuantity: typing.Optional[OrderedQuantityStatus] = None
    acknowledgementStatus: typing.Optional[AcknowledgementStatus] = None
    receivingStatus: typing.Optional[ReceivingStatus] = None


class OrderStatus(pydantic.BaseModel):
    purchaseOrderNumber: str
    purchaseOrderStatus: PurchaseOrderStatus
    purchaseOrderDate: str
    sellingParty: PartyIdentification
    shipToParty: PartyIdentification
    itemStatus: typing.List[OrderItemStatus]
    lastUpdatedDate: typing.Optional[str] = None


class OrderListStatus(pydantic.BaseModel):
    pagination: typing.Optional[Pagination] = None
    ordersStatus: typing.Optional[typing.List[OrderStatus]] = None


class GetPurchaseOrdersStatusResponse(pydantic.BaseModel):
    payload: typing.Optional[OrderListStatus] = None
    errors: typing.Optional[typing.List[Error]] = None


class GetPurchaseOrdersStatusQuery(pydantic.BaseModel):
    limit: typing.Optional[int] = None
    sortOrder: typing.Optional[SortOrder] = None
    nextToken: typing.Optional[str] = None
    createdAfter: typing.Optional[str] = None
    createdBefore: typing.Optional[str] = None
    updatedAfter: typing.Optional[str] = None
    updatedBefore: typing.Optional[str] = None
    purchaseOrderNumber: typing.Optional[str] = None
    purchaseOrderStatus: typing.Optional[PurchaseOrderStatus] = None
    itemConfirmationStatus: typing.Optional[ItemConfirmationStatus] = None
    itemReceiveStatus: typing.Optional[ItemReceiveStatus] = None
    orderingVendorCode: typing.Optional[str] = None
    shipToPartyId: typing.Optional[str] = None
