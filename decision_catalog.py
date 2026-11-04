"""Persistence for real dining choices; demo restaurant IDs never enter this API."""

from real_catalog import get_public_real_merchant, public_real_merchants


def initialize_decision_tables(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS real_favorites (
            session_id TEXT NOT NULL REFERENCES sessions(id),
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(session_id, merchant_id)
        )
    """
    )


def list_public_merchants(connection):
    """Read every public page, so ranking is not limited to the first 100 rows."""
    offset = 0
    while True:
        page = public_real_merchants(connection, limit=100, offset=offset)
        yield from page["items"]
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            return


def require_public_merchant(connection, merchant_id):
    try:
        merchant_id = int(merchant_id)
    except (TypeError, ValueError) as error:
        raise ValueError("门店编号无效") from error
    item = get_public_real_merchant(connection, merchant_id)
    if item is None:
        raise ValueError("门店资料不存在或已过期，请重新选择")
    return item


def set_real_favorite(connection, session_id, merchant_id, active):
    if not isinstance(active, bool):
        raise ValueError("收藏操作需要明确的状态")
    if active:
        item = require_public_merchant(connection, merchant_id)
        connection.execute(
            "INSERT OR IGNORE INTO real_favorites(session_id,merchant_id) VALUES (?,?)",
            (session_id, item["id"]),
        )
    else:
        # An expired record may still be removed from a visitor's collection.
        connection.execute(
            "DELETE FROM real_favorites WHERE session_id=? AND merchant_id=?",
            (session_id, int(merchant_id)),
        )


def saved_real_merchants(connection, session_id):
    result = []
    for row in connection.execute(
        "SELECT merchant_id FROM real_favorites WHERE session_id=? ORDER BY created_at DESC, merchant_id DESC",
        (session_id,),
    ):
        item = get_public_real_merchant(connection, row["merchant_id"])
        if item is not None:
            result.append(item)
    return result
