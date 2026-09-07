import pytest

import amzn_selling_partner as sp


def test_report_models_accept_documented_values() -> None:
    report_options = sp.reports.ReportOptions(reportPeriod="DAY")
    specification = sp.reports.CreateReportSpecification(
        reportType=sp.reports.ReportType.VENDOR_INVENTORY_REPORT,
        marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
        reportOptions=report_options,
    )
    query = sp.reports.GetReportsQuery(
        reportTypes=[sp.reports.ReportType.VENDOR_INVENTORY_REPORT],
        marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
    )

    assert specification.model_dump()["reportOptions"] == {
        "reportPeriod": sp.reports.ReportPeriod.DAY,
        "distributorView": None,
        "sellingProgram": None,
    }
    assert query.reportTypes == [sp.reports.ReportType.VENDOR_INVENTORY_REPORT]


def test_report_models_reject_undocumented_values() -> None:
    with pytest.raises(ValueError):
        sp.reports.CreateReportSpecification(
            reportType="FEE_DISCOUNTS_REPORT",
            marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
        )

    with pytest.raises(ValueError):
        sp.reports.ReportOptions(customOption="value")


def test_marketplace_id_spain_is_available() -> None:
    assert sp.reports.MarketPlaceId.SPAIN.value == "A1RKKUPIHCS9HS"


def test_report_schedule_models_validate_current_values() -> None:
    specification = sp.reports.CreateReportScheduleSpecification(
        reportType=sp.reports.ReportType.VENDOR_SALES_REPORT,
        marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
        period=sp.reports.SchedulePeriod.ONE_DAY,
    )
    schedule = sp.reports.ReportSchedule(
        reportScheduleId="schedule-id",
        reportType=sp.reports.ReportType.VENDOR_SALES_REPORT,
        period=sp.reports.SchedulePeriod.ONE_DAY,
    )

    assert specification.period == sp.reports.SchedulePeriod.ONE_DAY
    assert sp.reports.ReportScheduleList(reportSchedules=[schedule]).reportSchedules == [schedule]
