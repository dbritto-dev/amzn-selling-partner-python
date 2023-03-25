# Built-in packages
import enum
import typing

# Third-party packages
import pydantic


class ReportType(str, enum.Enum):
    VENDOR_SALES_REPORT = "GET_VENDOR_SALES_REPORT"
    VENDOR_TRAFFIC_REPORT = "GET_VENDOR_TRAFFIC_REPORT"
    VENDOR_FORECASTING_REPORT = "GET_VENDOR_FORECASTING_REPORT"
    VENDOR_INVENTORY_REPORT = "GET_VENDOR_INVENTORY_REPORT"


class MarketPlaceId(str, enum.Enum):
    CANADA = "A2EUQ1WTGCTBG2"
    UNITED_STATES_OF_AMERICA = "ATVPDKIKX0DER"
    MEXICO = "A1AM78C64UM0Y8"
    BRAZIL = "A2Q3Y263D00KWC"
    PAIN = "A1RKKUPIHCS9HS"
    UNITED_KINGDOM = "A1F83G8C2ARO7P"
    FRANCE = "A13V1IB3VIYZZH"
    BELGIUM = "AMEN7PMS3EDWL"
    NETHERLANDS = "A1805IZSGTT6HS"
    GERMANY = "A1PA6795UKMFR9"
    ITALY = "APJ6JRA9NG5V4"
    SWEDEN = "A2NODRKZP88ZB9"
    POLAND = "A1C3SOZRARQ6R3"
    EGYPT = "ARBP9OOSHTCHU"
    TURKEY = "A33AVAJ2PDY3EV"
    SAUDI_ARABIA = "A17E79C6D8DWNP"
    UNITED_ARAB_EMIRATES = "A2VIGQ35RCS4UG"
    INDIA = "A21TJRUUN4KGV"
    SINGAPORE = "A19VAU5U5O7RUS"
    AUSTRALIA = "A39IBJ37TRP1C6"
    JAPAN = "A1VC38T7YXB528"


class ProcessingStatus(str, enum.Enum):
    CANCELLED = "CANCELLED"
    DONE = "DONE"
    FATAL = "FATAL"
    IN_PROGRESS = "IN_PROGRESS"
    IN_QUEUE = "IN_QUEUE"


class CompressionAlgorithm(str, enum.Enum):
    GZIP = "GZIP"


class ReportPeriod(str, enum.Enum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"


class DistributorView(str, enum.Enum):
    SOURCING = "SOURCING"
    MANUFACTURING = "MANUFACTURING"


class SellingProgram(str, enum.Enum):
    RETAIL = "RETAIL"
    BUSINESS = "BUSINESS"
    FRESH = "FRESH"


class ReportOptions(pydantic.BaseModel):
    reportPeriod: typing.Optional[ReportPeriod] = None
    distributorView: typing.Optional[DistributorView] = None
    sellingProgram: typing.Optional[SellingProgram] = None


class CreateReportSpecification(pydantic.BaseModel):
    reportType: ReportType
    marketplaceIds: typing.List[MarketPlaceId]
    reportOptions: typing.Optional[ReportOptions] = None
    dataStartTime: typing.Optional[str] = None
    dataEndTime: typing.Optional[str] = None


class CreateReportResponse(pydantic.BaseModel):
    reportId: str


class GetReportsQuery(pydantic.BaseModel):
    reportTypes: typing.Optional[typing.List[ReportType]] = None
    processingStatuses: typing.Optional[typing.List[ProcessingStatus]] = None
    marketplaceIds: typing.Optional[typing.List[MarketPlaceId]] = None
    pageSize: typing.Optional[int] = None
    createdSince: typing.Optional[str] = None
    createdUntil: typing.Optional[str] = None
    nextToken: typing.Optional[str] = None


class Report(pydantic.BaseModel):
    reportId: str
    reportType: ReportType
    createdTime: str
    processingStatus: ProcessingStatus
    marketplaceIds: typing.Optional[typing.List[MarketPlaceId]] = None
    dataStartTime: typing.Optional[str] = None
    dataEndTime: typing.Optional[str] = None
    reportScheduleId: typing.Optional[str] = None
    processingStartTime: typing.Optional[str] = None
    processingEndTime: typing.Optional[str] = None
    reportDocumentId: typing.Optional[str] = None


class GetReportsResponse(pydantic.BaseModel):
    reports: typing.List[Report]
    nextToken: typing.Optional[str] = None


class ReportDocument(pydantic.BaseModel):
    reportDocumentId: str
    url: str
    compressionAlgorithm: typing.Optional[CompressionAlgorithm] = None
