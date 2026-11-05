"""Dates describe different evidence: online collection is not a field survey."""

from datetime import date

CATALOG_YEARS = 5
PHOTO_YEARS = 2


def cutoff_date(years, reference=None):
    today = reference or date.today()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def catalog_cutoff(reference=None):
    return cutoff_date(CATALOG_YEARS, reference)


def photo_cutoff(reference=None):
    return cutoff_date(PHOTO_YEARS, reference)


def clean_date(raw, label):
    if not raw:
        return ""
    try:
        value = date.fromisoformat(str(raw))
    except ValueError as error:
        raise ValueError(label + " 必须为 YYYY-MM-DD") from error
    if value > date.today():
        raise ValueError(label + " 不能晚于今天")
    return value.isoformat()
