"""Tests for the Silver transformation layer.

All tests use the local Spark session (no Azure required).
"""



class TestCustomerTransform:
    def test_email_is_lowercased(self, spark):
        """Emails must be normalised to lowercase."""
        from etl.silver.transform_customers import _cleanse_customers

        data = [(1, "Test User", "TEST.User@Company.DE", "Corp GmbH", 10)]
        df = spark.createDataFrame(data, ["customer_id", "name", "email", "company", "address_id"])
        valid, _ = _cleanse_customers(df)
        email = valid.select("email").first()[0]
        assert email == "test.user@company.de"

    def test_invalid_email_quarantined(self, spark):
        """Rows with invalid email addresses must go to quarantine."""
        from etl.silver.transform_customers import _cleanse_customers

        data = [
            (1, "Valid User",   "valid@example.de",  "Corp A", 10),
            (2, "Invalid User", "not-an-email",       "Corp B", 11),
            (3, "Also Bad",     "@nodomain",          "Corp C", 12),
        ]
        df = spark.createDataFrame(data, ["customer_id", "name", "email", "company", "address_id"])
        valid, quarantine = _cleanse_customers(df)

        assert valid.count() == 1
        assert quarantine.count() == 2

    def test_null_customer_id_quarantined(self, spark):
        """Rows with null customer_id must be quarantined."""
        from pyspark.sql.types import IntegerType, StringType, StructField, StructType

        from etl.silver.transform_customers import _cleanse_customers

        schema = StructType([
            StructField("customer_id", IntegerType(), True),
            StructField("name", StringType(), True),
            StructField("email", StringType(), True),
            StructField("company", StringType(), True),
            StructField("address_id", IntegerType(), True),
        ])
        data = [(None, "User", "u@example.de", "Corp", 10)]
        df = spark.createDataFrame(data, schema)
        valid, quarantine = _cleanse_customers(df)

        assert valid.count() == 0
        assert quarantine.count() == 1

    def test_name_whitespace_trimmed(self, spark):
        """Leading/trailing whitespace must be stripped from name field."""
        from etl.silver.transform_customers import _cleanse_customers

        data = [(1, "  Thomas Müller  ", "t@example.de", "Corp", 10)]
        df = spark.createDataFrame(data, ["customer_id", "name", "email", "company", "address_id"])
        valid, _ = _cleanse_customers(df)
        name = valid.select("name").first()[0]
        assert name == "Thomas Müller"


class TestOrderTransform:
    def test_status_uppercased(self, spark):
        """Order status must be normalised to uppercase."""
        from etl.silver.transform_orders import _cleanse_orders

        data = [
            (1, 1, "2024-01-01", "delivered", 10),
            (2, 2, "2024-02-01", "Shipped",   11),
        ]
        df = spark.createDataFrame(data, ["order_id", "customer_id", "order_date", "status", "shipping_address_id"])
        valid, _ = _cleanse_orders(df)
        statuses = {row.status for row in valid.select("status").collect()}
        assert statuses == {"DELIVERED", "SHIPPED"}

    def test_invalid_status_quarantined(self, spark):
        """Orders with unknown status values must be quarantined."""
        from etl.silver.transform_orders import _cleanse_orders

        data = [
            (1, 1, "2024-01-01", "DELIVERED", 10),
            (2, 2, "2024-02-01", "UNKNOWN",   11),
            (3, 3, "2024-03-01", "BROKEN",    12),
        ]
        df = spark.createDataFrame(data, ["order_id", "customer_id", "order_date", "status", "shipping_address_id"])
        valid, quarantine = _cleanse_orders(df)

        assert valid.count() == 1
        assert quarantine.count() == 2

    def test_line_revenue_calculated(self, spark):
        """Silver order items must have a computed line_revenue column."""
        from decimal import Decimal

        from pyspark.sql.types import DecimalType, IntegerType, StructField, StructType

        from etl.silver.transform_orders import _cleanse_order_items

        schema = StructType([
            StructField("order_item_id", IntegerType()),
            StructField("order_id", IntegerType()),
            StructField("product_id", IntegerType()),
            StructField("quantity", IntegerType()),
            StructField("unit_price", DecimalType(10, 2)),
            StructField("discount_pct", DecimalType(5, 2)),
        ])
        data = [(1, 1, 1, 10, Decimal("100.00"), Decimal("10.00"))]
        df = spark.createDataFrame(data, schema)
        valid, _ = _cleanse_order_items(df)

        revenue = float(valid.select("line_revenue").first()[0])
        # 10 * 100 * (1 - 0.10) = 900.00
        assert abs(revenue - 900.00) < 0.01

    def test_zero_quantity_quarantined(self, spark):
        """Order items with quantity <= 0 must be quarantined."""
        from decimal import Decimal

        from pyspark.sql.types import DecimalType, IntegerType, StructField, StructType

        from etl.silver.transform_orders import _cleanse_order_items

        schema = StructType([
            StructField("order_item_id", IntegerType()),
            StructField("order_id", IntegerType()),
            StructField("product_id", IntegerType()),
            StructField("quantity", IntegerType()),
            StructField("unit_price", DecimalType(10, 2)),
            StructField("discount_pct", DecimalType(5, 2)),
        ])
        data = [
            (1, 1, 1, 0,  Decimal("10.00"), Decimal("0.00")),  # invalid
            (2, 1, 2, -1, Decimal("10.00"), Decimal("0.00")),  # invalid
            (3, 1, 3, 5,  Decimal("10.00"), Decimal("0.00")),  # valid
        ]
        df = spark.createDataFrame(data, schema)
        valid, quarantine = _cleanse_order_items(df)
        assert valid.count() == 1
        assert quarantine.count() == 2


class TestProductTransform:
    def test_sku_uppercased(self, spark):
        """SKUs must be normalised to uppercase."""
        from decimal import Decimal

        from pyspark.sql.types import (
            DecimalType,
            IntegerType,
            StringType,
            StructField,
            StructType,
        )

        from etl.silver.transform_products import _cleanse_products

        schema = StructType([
            StructField("product_id", IntegerType()),
            StructField("sku", StringType()),
            StructField("name", StringType()),
            StructField("description", StringType()),
            StructField("category_name", StringType()),
            StructField("supplier_name", StringType()),
            StructField("list_price", DecimalType(10, 2)),
            StructField("stock_qty", IntegerType()),
            StructField("supplier_id", IntegerType()),
        ])
        data = [(1, "shf-001", "Shelf", "Desc", "Shelving", "Supplier", Decimal("10.00"), 5, 1)]
        df = spark.createDataFrame(data, schema)
        valid, _ = _cleanse_products(df)
        sku = valid.select("sku").first()[0]
        assert sku == "SHF-001"

    def test_negative_price_quarantined(self, spark):
        """Products with negative list_price must be quarantined."""
        from decimal import Decimal

        from pyspark.sql.types import (
            DecimalType,
            IntegerType,
            StringType,
            StructField,
            StructType,
        )

        from etl.silver.transform_products import _cleanse_products

        schema = StructType([
            StructField("product_id", IntegerType()),
            StructField("sku", StringType()),
            StructField("name", StringType()),
            StructField("description", StringType()),
            StructField("category_name", StringType()),
            StructField("supplier_name", StringType()),
            StructField("list_price", DecimalType(10, 2)),
            StructField("stock_qty", IntegerType()),
            StructField("supplier_id", IntegerType()),
        ])
        data = [(1, "BAD-001", "Bad Product", "Desc", "Cat", "Sup", Decimal("-5.00"), 5, 1)]
        df = spark.createDataFrame(data, schema)
        valid, quarantine = _cleanse_products(df)
        assert valid.count() == 0
        assert quarantine.count() == 1
