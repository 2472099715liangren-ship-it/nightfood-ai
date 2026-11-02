"""Database access and schema setup for NightFind.

Keep SQL and persistence details in this module. Business rules live in services.py.
"""
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("APP_DB", ROOT / "data" / "night.db"))


def connect():
    """Return a configured SQLite connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _add_missing_columns(connection):
    """Migrate older project databases without deleting existing records."""
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(restaurants)")
    }
    migrations = {
        "description": "TEXT NOT NULL DEFAULT ''",
        "address_label": "TEXT NOT NULL DEFAULT ''",
        "source_note": "TEXT NOT NULL DEFAULT '研究原型模拟数据'",
    }
    for name, definition in migrations.items():
        if name not in columns:
            connection.execute(
                "ALTER TABLE restaurants ADD COLUMN " + name + " " + definition
            )


def initialize_database():
    """Create tables, apply safe additive migrations, and seed demo records once."""
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS districts (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                lat REAL,
                lng REAL
            );

            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY,
                district_id INTEGER REFERENCES districts(id),
                name TEXT NOT NULL,
                cuisine TEXT NOT NULL,
                price INTEGER NOT NULL,
                rating REAL NOT NULL DEFAULT 0,
                wait INTEGER NOT NULL DEFAULT 0,
                lat REAL,
                lng REAL,
                tags TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#DCE9D4',
                description TEXT NOT NULL DEFAULT '',
                address_label TEXT NOT NULL DEFAULT '',
                source_note TEXT NOT NULL DEFAULT '研究原型模拟数据'
            );

            CREATE TABLE IF NOT EXISTS hours (
                restaurant_id INTEGER PRIMARY KEY REFERENCES restaurants(id),
                opens INTEGER NOT NULL,
                closes INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dishes (
                id INTEGER PRIMARY KEY,
                restaurant_id INTEGER REFERENCES restaurants(id),
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recommendation_runs (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                constraints_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recommendation_items (
                id INTEGER PRIMARY KEY,
                run_id INTEGER REFERENCES recommendation_runs(id),
                restaurant_id INTEGER REFERENCES restaurants(id),
                score REAL,
                explanation TEXT
            );

            CREATE TABLE IF NOT EXISTS favorites (
                session_id TEXT REFERENCES sessions(id),
                restaurant_id INTEGER REFERENCES restaurants(id),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(session_id, restaurant_id)
            );

            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                scene TEXT,
                priority TEXT,
                trust INTEGER,
                willingness INTEGER,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                restaurant_id INTEGER REFERENCES restaurants(id),
                rating INTEGER,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                kind TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            -- Real-world restaurant data is kept separate from demo restaurants.
            CREATE TABLE IF NOT EXISTS wuhan_areas (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                area_type TEXT NOT NULL CHECK (
                    area_type IN ('administrative_district', 'development_zone')
                ),
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS restaurant_sources (
                id INTEGER PRIMARY KEY,
                source_code TEXT NOT NULL UNIQUE,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_homepage TEXT NOT NULL DEFAULT '',
                terms_url TEXT NOT NULL DEFAULT '',
                license_note TEXT NOT NULL,
                permission_status TEXT NOT NULL DEFAULT 'pending' CHECK (
                    permission_status IN ('pending', 'approved', 'suspended')
                ),
                approved_by TEXT NOT NULL DEFAULT '',
                approved_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS restaurant_import_batches (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES restaurant_sources(id),
                file_name TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,
                imported_by TEXT NOT NULL DEFAULT '',
                total_rows INTEGER NOT NULL DEFAULT 0,
                inserted_rows INTEGER NOT NULL DEFAULT 0,
                updated_rows INTEGER NOT NULL DEFAULT 0,
                review_rows INTEGER NOT NULL DEFAULT 0,
                error_rows INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, file_sha256)
            );

            CREATE TABLE IF NOT EXISTS real_restaurants (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL REFERENCES restaurant_sources(id),
                external_id TEXT NOT NULL,
                name TEXT NOT NULL,
                branch_name TEXT NOT NULL DEFAULT '',
                district TEXT NOT NULL,
                business_area TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                phone TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                cuisine TEXT NOT NULL DEFAULT '',
                price_per_person INTEGER,
                business_status TEXT NOT NULL DEFAULT 'unknown' CHECK (
                    business_status IN ('unknown', 'open', 'closed', 'temporarily_closed')
                ),
                description TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL,
                source_updated_at TEXT,
                record_status TEXT NOT NULL DEFAULT 'pending' CHECK (
                    record_status IN ('pending', 'verified', 'rejected', 'needs_review')
                ),
                verification_method TEXT NOT NULL DEFAULT '',
                verification_note TEXT NOT NULL DEFAULT '',
                verified_by TEXT NOT NULL DEFAULT '',
                verified_at TEXT,
                last_seen_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(source_id, external_id)
            );

            CREATE TABLE IF NOT EXISTS real_restaurant_hours (
                restaurant_id INTEGER NOT NULL REFERENCES real_restaurants(id) ON DELETE CASCADE,
                weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
                opens_at TEXT NOT NULL DEFAULT '',
                closes_at TEXT NOT NULL DEFAULT '',
                is_closed INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(restaurant_id, weekday)
            );

            CREATE TABLE IF NOT EXISTS real_restaurant_dishes (
                id INTEGER PRIMARY KEY,
                restaurant_id INTEGER NOT NULL REFERENCES real_restaurants(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                price INTEGER,
                source_url TEXT NOT NULL DEFAULT '',
                source_updated_at TEXT,
                record_status TEXT NOT NULL DEFAULT 'pending' CHECK (
                    record_status IN ('pending', 'verified', 'rejected')
                )
            );

            CREATE TABLE IF NOT EXISTS restaurant_import_errors (
                id INTEGER PRIMARY KEY,
                batch_id INTEGER NOT NULL REFERENCES restaurant_import_batches(id) ON DELETE CASCADE,
                row_number INTEGER NOT NULL,
                external_id TEXT NOT NULL DEFAULT '',
                error_code TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS restaurant_change_log (
                id INTEGER PRIMARY KEY,
                restaurant_id INTEGER NOT NULL REFERENCES real_restaurants(id) ON DELETE CASCADE,
                source_id INTEGER REFERENCES restaurant_sources(id),
                field_name TEXT NOT NULL,
                old_value TEXT NOT NULL DEFAULT '',
                new_value TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_real_restaurants_area
                ON real_restaurants(district, business_area);
            CREATE INDEX IF NOT EXISTS idx_real_restaurants_status
                ON real_restaurants(record_status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_real_restaurants_name
                ON real_restaurants(name);
            CREATE INDEX IF NOT EXISTS idx_real_restaurants_location
                ON real_restaurants(latitude, longitude);
            CREATE INDEX IF NOT EXISTS idx_restaurant_import_errors_batch
                ON restaurant_import_errors(batch_id);
            CREATE INDEX IF NOT EXISTS idx_restaurant_change_log_restaurant
                ON restaurant_change_log(restaurant_id, changed_at);

            CREATE INDEX IF NOT EXISTS idx_restaurants_district
                ON restaurants(district_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_restaurant
                ON feedback(restaurant_id);
            CREATE INDEX IF NOT EXISTS idx_suggestions_created
                ON suggestions(created_at);
            """
        )
        _add_missing_columns(connection)
        _seed_demo_data(connection)
        _seed_wuhan_areas(connection)
        _backfill_merchant_descriptions(connection)


def _seed_demo_data(connection):
    """Insert the sample Wuhan directory only when the database is empty."""
    if connection.execute("SELECT COUNT(*) FROM districts").fetchone()[0] == 0:
        districts = [
            ("江汉路", "老街巷与城市夜生活交织", 30.586, 114.291),
            ("楚河汉街", "适合散步、聚餐和慢慢挑选晚餐", 30.557, 114.342),
            ("光谷步行街", "年轻人常去的夜间消费片区", 30.506, 114.402),
            ("粮道街", "街巷里的武汉风味与小吃", 30.545, 114.307),
        ]
        connection.executemany(
            "INSERT INTO districts(name, description, lat, lng) VALUES (?, ?, ?, ?)",
            districts,
        )

    if connection.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0] > 0:
        return

    samples = [
        ("江城炭火烧烤", "烧烤", 65, "朋友聚会,烟火气", "#D9B48F",
         "适合慢慢聊天的炭火烧烤风味小馆。"),
        ("巷里小龙虾", "小龙虾", 98, "朋友聚会,武汉特色", "#E8B6A5",
         "以小龙虾和分享式菜品为主题的夜宵小馆。"),
        ("一碗热干面", "湖北菜", 22, "独自用餐,武汉特色", "#E8D8A7",
         "适合简单吃一餐的武汉风味面食档口。"),
        ("深夜食堂·小馆", "家常菜", 48, "独自用餐,安静", "#C9D9B9",
         "以家常菜为主，适合不想吃得太复杂的晚上。"),
        ("沿江鲜鱼馆", "湖北菜", 86, "朋友聚会,武汉特色", "#B9D3D0",
         "以鱼类和湖北家常风味为主题的聚餐小馆。"),
        ("街角砂锅粥", "粥粉面", 35, "清淡,独自用餐", "#E4D7BC",
         "口味相对清爽，适合想吃热乎简餐的时候。"),
    ]
    districts = connection.execute(
        "SELECT id, name, lat, lng FROM districts ORDER BY id"
    ).fetchall()

    for district_index, district in enumerate(districts):
        for item_index, sample in enumerate(samples):
            name, cuisine, price, tags, color, description = sample
            restaurant_id = district_index * len(samples) + item_index + 1
            connection.execute(
                """
                INSERT INTO restaurants (
                    id, district_id, name, cuisine, price, rating, wait,
                    lat, lng, tags, color, description, address_label, source_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    restaurant_id,
                    district["id"],
                    name + " · " + district["name"],
                    cuisine,
                    price + district_index * 3,
                    round(4.3 + (item_index % 4) * 0.2, 1),
                    8 + item_index * 5,
                    district["lat"] + 0.003 * (item_index - 2),
                    district["lng"] + 0.004 * (item_index % 3 - 1),
                    tags,
                    color,
                    description,
                    district["name"] + "（示例商圈，非真实门牌）",
                    "研究原型模拟数据",
                ),
            )
            close_hour = 28 if item_index % 3 == 0 else 26
            connection.execute(
                "INSERT INTO hours(restaurant_id, opens, closes) VALUES (?, ?, ?)",
                (restaurant_id, 17, close_hour),
            )
            dish_names = ["招牌推荐", "时令小菜", "店内小食"]
            for dish_index, dish_name in enumerate(dish_names):
                connection.execute(
                    """
                    INSERT INTO dishes(restaurant_id, name, price)
                    VALUES (?, ?, ?)
                    """,
                    (
                        restaurant_id,
                        cuisine + dish_name,
                        max(8, price // (dish_index + 1)),
                    ),
                )


def _seed_wuhan_areas(connection):
    """Create Wuhan's administrative coverage and separately label functional zones."""
    areas = [
        ("江岸区", "administrative_district", 10),
        ("江汉区", "administrative_district", 20),
        ("硚口区", "administrative_district", 30),
        ("汉阳区", "administrative_district", 40),
        ("武昌区", "administrative_district", 50),
        ("青山区", "administrative_district", 60),
        ("洪山区", "administrative_district", 70),
        ("蔡甸区", "administrative_district", 80),
        ("江夏区", "administrative_district", 90),
        ("黄陂区", "administrative_district", 100),
        ("新洲区", "administrative_district", 110),
        ("东西湖区", "administrative_district", 120),
        ("汉南区", "administrative_district", 130),
        ("东湖高新区", "development_zone", 210),
        ("武汉经开区", "development_zone", 220),
        ("长江新区", "development_zone", 230),
        ("东湖风景区", "development_zone", 240),
    ]
    connection.executemany(
        """
        INSERT OR IGNORE INTO wuhan_areas(name, area_type, sort_order)
        VALUES (?, ?, ?)
        """,
        areas,
    )


def _backfill_merchant_descriptions(connection):
    """Give older seeded rows readable descriptions after schema migration."""
    connection.execute(
        """
        UPDATE restaurants
        SET description = '以' || cuisine || '为主的夜间餐饮示例商户，适合'
            || REPLACE(tags, ',', '、') || '等就餐场景。'
        WHERE description IS NULL OR description = ''
        """
    )
    connection.execute(
        """
        UPDATE restaurants
        SET address_label = (
            SELECT name || '（示例商圈，非真实门牌）'
            FROM districts WHERE districts.id = restaurants.district_id
        )
        WHERE address_label IS NULL OR address_label = ''
        """
    )


def ensure_session(connection, session_id):
    connection.execute(
        "INSERT OR IGNORE INTO sessions(id) VALUES (?)", (session_id,)
    )


def _merchant_dict(row):
    merchant = dict(row)
    merchant["tags"] = [
        value for value in (merchant.get("tags") or "").split(",") if value
    ]
    merchant["is_demo"] = True
    return merchant


def list_merchants(
    connection, keyword="", district="", cuisine="", max_price=None, limit=100
):
    """Search the merchant directory with parameterized filters."""
    conditions = []
    parameters = []

    if keyword:
        pattern = "%" + keyword.strip()[:80] + "%"
        conditions.append(
            "(r.name LIKE ? OR r.cuisine LIKE ? OR r.description LIKE ?)"
        )
        parameters.extend([pattern, pattern, pattern])

    if district:
        conditions.append("d.name = ?")
        parameters.append(district)

    if cuisine and cuisine != "不限":
        conditions.append("r.cuisine = ?")
        parameters.append(cuisine)

    if max_price is not None:
        conditions.append("r.price <= ?")
        parameters.append(max_price)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = """
        SELECT
            r.id, r.name, r.cuisine, r.price, r.rating, r.wait,
            r.tags, r.color, r.description, r.address_label, r.source_note, r.lat, r.lng,
            d.name AS district, h.opens, h.closes,
            COALESCE(review_stats.review_count, 0) AS review_count,
            review_stats.average_rating AS user_rating
        FROM restaurants AS r
        JOIN districts AS d ON d.id = r.district_id
        LEFT JOIN hours AS h ON h.restaurant_id = r.id
        LEFT JOIN (
            SELECT restaurant_id, COUNT(*) AS review_count,
                   ROUND(AVG(rating), 1) AS average_rating
            FROM feedback GROUP BY restaurant_id
        ) AS review_stats ON review_stats.restaurant_id = r.id
    """ + where_clause + " ORDER BY r.name LIMIT ?"
    parameters.append(max(1, min(int(limit), 200)))
    rows = connection.execute(query, parameters).fetchall()
    return [_merchant_dict(row) for row in rows]


def get_merchant(connection, merchant_id):
    row = connection.execute(
        """
        SELECT r.*, d.name AS district, h.opens, h.closes
        FROM restaurants AS r
        JOIN districts AS d ON d.id = r.district_id
        LEFT JOIN hours AS h ON h.restaurant_id = r.id
        WHERE r.id = ?
        """,
        (merchant_id,),
    ).fetchone()
    if row is None:
        return None

    merchant = _merchant_dict(row)
    merchant["dishes"] = [
        dict(dish)
        for dish in connection.execute(
            "SELECT name, price FROM dishes WHERE restaurant_id = ? ORDER BY id",
            (merchant_id,),
        )
    ]
    merchant["reviews"] = [
        dict(review)
        for review in connection.execute(
            """
            SELECT rating, comment, created_at FROM feedback
            WHERE restaurant_id = ? ORDER BY id DESC LIMIT 10
            """,
            (merchant_id,),
        )
    ]
    return merchant


def list_districts(connection):
    return [
        dict(row)
        for row in connection.execute(
            "SELECT id, name, description FROM districts ORDER BY id"
        )
    ]


def save_recommendation_run(connection, session_id, preferences, items):
    cursor = connection.execute(
        """
        INSERT INTO recommendation_runs(session_id, constraints_json)
        VALUES (?, ?)
        """,
        (session_id, json.dumps(preferences, ensure_ascii=False)),
    )
    run_id = cursor.lastrowid
    connection.executemany(
        """
        INSERT INTO recommendation_items(run_id, restaurant_id, score, explanation)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                run_id,
                item["id"],
                item["score"],
                item["explanation"],
            )
            for item in items
        ],
    )


def list_favorites(connection, session_id):
    return [
        row["restaurant_id"]
        for row in connection.execute(
            "SELECT restaurant_id FROM favorites WHERE session_id = ? "
            "ORDER BY created_at DESC, restaurant_id DESC",
            (session_id,),
        )
    ]


def list_saved_merchants(connection, session_id):
    """Return the current visitor's saved shops, newest first.

    This uses the existing favorites table. Saving is scoped to the browser's
    anonymous session; there is no cross-device account synchronization.
    """
    saved = list_favorites(connection, session_id)
    if not saved:
        return []
    catalog = {
        merchant["id"]: merchant for merchant in list_merchants(connection, limit=200)
    }
    return [catalog[merchant_id] for merchant_id in saved if merchant_id in catalog]


def set_favorite(connection, session_id, merchant_id, active):
    if active:
        connection.execute(
            """
            INSERT OR IGNORE INTO favorites(session_id, restaurant_id)
            VALUES (?, ?)
            """,
            (session_id, merchant_id),
        )
    else:
        connection.execute(
            "DELETE FROM favorites WHERE session_id = ? AND restaurant_id = ?",
            (session_id, merchant_id),
        )


def create_suggestion(connection, session_id, category, message):
    allowed = {"功能建议", "商家信息", "使用体验", "其他"}
    if category not in allowed:
        raise ValueError("请选择有效的建议分类")
    message = str(message).strip()
    if not message or len(message) > 2000:
        raise ValueError("建议内容需为 1–2000 个字符")
    connection.execute(
        """
        INSERT INTO suggestions(session_id, category, message)
        VALUES (?, ?, ?)
        """,
        (session_id, category, message),
    )


def suggestion_summary(connection):
    total = connection.execute(
        "SELECT COUNT(*) FROM suggestions"
    ).fetchone()[0]
    categories = [
        dict(row)
        for row in connection.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM suggestions GROUP BY category ORDER BY count DESC
            """
        )
    ]
    return {"total": total, "categories": categories}


def create_feedback(connection, session_id, merchant_id, rating, comment):
    try:
        merchant_id = int(merchant_id)
    except (TypeError, ValueError) as error:
        raise ValueError("请选择有效商户") from error
    exists = connection.execute(
        "SELECT 1 FROM restaurants WHERE id = ?", (merchant_id,)
    ).fetchone()
    if exists is None:
        raise ValueError("没有找到这家商户")
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("评分范围为 1–5")
    connection.execute(
        """
        INSERT INTO feedback(session_id, restaurant_id, rating, comment)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, merchant_id, rating, str(comment).strip()[:2000]),
    )


def review_summary(connection):
    summary = connection.execute(
        """
        SELECT COUNT(*) AS total, ROUND(AVG(rating), 1) AS average
        FROM feedback
        """
    ).fetchone()
    return dict(summary)


def list_reviews(connection, limit=100):
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT f.id, f.restaurant_id, r.name AS merchant_name,
                   f.rating, f.comment, f.created_at
            FROM feedback AS f
            JOIN restaurants AS r ON r.id = f.restaurant_id
            ORDER BY f.id DESC LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        )
    ]
