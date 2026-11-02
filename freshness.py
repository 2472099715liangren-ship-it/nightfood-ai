"""Two-calendar-year freshness policy for Wuhan's verified real-world catalog.

Freshness is checked at import, at review and at public read time. The
requirements apply to source observations and storefront photographs.
"""
from datetime import date


def today():
    return date.today()


def cutoff_date(reference=None):
    reference = reference or today()
    try:
        return reference.replace(year=reference.year - 2)
    except ValueError:
        # On February 29, the corresponding day two years earlier is February 28.
        return reference.replace(year=reference.year - 2, day=28)


def parse_recent_date(value, label="资料日期", reference=None):
    """Parse YYYY-MM-DD and reject missing, future or >2-year-old evidence."""
    from datetime import datetime

    reference = reference or today()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("{}不能为空；必须有近两年内的可追溯记录".format(label))
    value = value.strip()
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("{}请填写 YYYY-MM-DD 日期".format(label)) from error
    if parsed > reference:
        raise ValueError("{}不能晚于当前日期".format(label))
    if parsed < cutoff_date(reference):
        raise ValueError("{}已超过两年，请先取得更新资料".format(label))
    return parsed.isoformat()


def recent_sql(alias="r"):
    """Condition for public records; combine with source permission + verified."""
    # The validation layer normalizes dates to YYYY-MM-DD.
    return (
        f"AND {alias}.source_updated_at >= ? "
        f"AND substr({alias}.verified_at, 1, 10) >= ?"
    )


def recent_parameters(reference=None):
    boundary = cutoff_date(reference).isoformat()
    return [boundary, boundary]
