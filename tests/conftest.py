"""Pytest configuration: shared PySpark fixtures for all test modules.

Tests run in local Spark mode — no Azure credentials or cluster needed.
Delta Lake is available via the delta-spark package.
"""

import os
import shutil
import tempfile

import pytest
from pyspark.sql import SparkSession

# Force local mode for all tests
os.environ["SPARK_ENV"] = "local"


@pytest.fixture(scope="session")
def spark() -> SparkSession:
    """Session-scoped SparkSession in local mode with Delta Lake enabled."""
    session = (
        SparkSession.builder.appName("test")
        .master("local[1]")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.sql.warehouse.dir", "/tmp/test-spark-warehouse")
        .config("spark.driver.memory", "1g")
        .config("spark.ui.enabled", "false")  # disable Spark UI in tests
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def tmp_storage(tmp_path) -> str:
    """Provides a temporary directory simulating the storage account root.

    Creates bronze/, silver/, gold/, and quarantine/ sub-directories.
    Returns the base path string (no abfss:// prefix — local paths for tests).
    """
    base = str(tmp_path)
    for layer in ("bronze", "silver", "gold", "quarantine"):
        os.makedirs(os.path.join(base, layer), exist_ok=True)
    return base


@pytest.fixture
def sample_customers(spark):
    """Small DataFrame of valid customer records."""
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType

    schema = StructType([
        StructField("customer_id", IntegerType(), False),
        StructField("name", StringType(), True),
        StructField("email", StringType(), True),
        StructField("company", StringType(), True),
        StructField("address_id", IntegerType(), True),
        StructField("city", StringType(), True),
        StructField("country_code", StringType(), True),
    ])
    data = [
        (1, "Thomas Müller", "t.mueller@logistik-nord.de", "Logistik Nord GmbH", 10, "Köln", "DE"),
        (2, "Sandra Bauer",  "s.bauer@techfabrik.de",      "TechFabrik GmbH",    11, "Frankfurt", "DE"),
        (3, "Klaus Weber",   "k.weber@lagerpro.de",         "LagerPro AG",        12, "Bremen", "DE"),
    ]
    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_products(spark):
    """Small DataFrame of valid product records."""
    from pyspark.sql.types import (DecimalType, IntegerType, StringType,
                                   StructField, StructType)

    schema = StructType([
        StructField("product_id", IntegerType(), False),
        StructField("sku", StringType(), False),
        StructField("name", StringType(), False),
        StructField("description", StringType(), True),
        StructField("category_name", StringType(), True),
        StructField("supplier_name", StringType(), True),
        StructField("list_price", DecimalType(10, 2), False),
        StructField("stock_qty", IntegerType(), False),
        StructField("supplier_id", IntegerType(), True),
    ])
    data = [
        (1, "SHF-001", "Heavy Duty Shelving 200x100", "5 shelves, 300 kg", "Shelving Systems", "SSI Schäfer", 189.90, 50, 3),
        (2, "PLT-001", "Euro Pallet 800x1200",        "EPAL wooden pallet", "Pallets & Containers", "Craemer", 12.50, 500, 7),
        (3, "PPE-001", "Safety Helmet EN397",         "ABS shell",          "PPE", "3M", 12.90, 100, 10),
    ]
    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_orders(spark):
    """Small DataFrame of valid order records."""
    from pyspark.sql.types import IntegerType, StringType, StructField, StructType, TimestampType
    import datetime

    schema = StructType([
        StructField("order_id", IntegerType(), False),
        StructField("customer_id", IntegerType(), False),
        StructField("order_date", StringType(), True),
        StructField("status", StringType(), True),
        StructField("shipping_address_id", IntegerType(), True),
    ])
    data = [
        (1, 1, "2024-01-15 00:00:00", "DELIVERED", 10),
        (2, 2, "2024-06-01 00:00:00", "SHIPPED",   11),
        (3, 3, "2025-01-10 00:00:00", "PENDING",   12),
    ]
    return spark.createDataFrame(data, schema)


@pytest.fixture
def sample_order_items(spark):
    """Small DataFrame of valid order item records."""
    from decimal import Decimal
    from pyspark.sql.types import (DecimalType, IntegerType, StructField, StructType)

    schema = StructType([
        StructField("order_item_id", IntegerType(), False),
        StructField("order_id", IntegerType(), False),
        StructField("product_id", IntegerType(), False),
        StructField("quantity", IntegerType(), False),
        StructField("unit_price", DecimalType(10, 2), False),
        StructField("discount_pct", DecimalType(5, 2), False),
    ])
    data = [
        (1, 1, 1, 2, Decimal("189.90"), Decimal("0.00")),
        (2, 1, 2, 100, Decimal("12.50"), Decimal("5.00")),
        (3, 2, 3, 10, Decimal("12.90"), Decimal("10.00")),
    ]
    return spark.createDataFrame(data, schema)
