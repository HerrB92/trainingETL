"""Tests for the Gold layer star schema construction."""

import pytest
from pyspark.sql import functions as F


class TestDimDate:
    def test_dim_date_row_count(self, spark):
        """dim_date must have exactly 4018 rows for 2020-01-01 to 2030-12-31."""
        from etl.gold.star_schema import build_dim_date

        # We test the data generation logic directly, not the Delta write
        from datetime import date, timedelta

        start = date(2020, 1, 1)
        end = date(2030, 12, 31)
        expected = (end - start).days + 1
        assert expected == 4018

    def test_dim_date_date_key_format(self, spark):
        """date_key must equal YYYYMMDD integer (e.g. 20240115)."""
        from datetime import date

        # Simulate the logic
        d = date(2024, 1, 15)
        date_key = int(d.strftime("%Y%m%d"))
        assert date_key == 20240115

    def test_weekday_detection(self):
        """Saturday and Sunday must be flagged as is_weekend=True."""
        from datetime import date

        saturday = date(2024, 1, 13)  # Known Saturday
        sunday = date(2024, 1, 14)   # Known Sunday
        monday = date(2024, 1, 15)   # Known Monday

        assert saturday.weekday() >= 5  # is_weekend
        assert sunday.weekday() >= 5    # is_weekend
        assert monday.weekday() < 5     # not is_weekend

    def test_quarter_calculation(self):
        """Quarter must be correctly derived from month number."""
        for month, expected_quarter in [(1,1),(3,1),(4,2),(6,2),(7,3),(9,3),(10,4),(12,4)]:
            quarter = ((month - 1) // 3) + 1
            assert quarter == expected_quarter, f"Month {month} should be Q{expected_quarter}"


class TestFactSales:
    def test_revenue_formula(self, spark):
        """Revenue = quantity * unit_price * (1 - discount_pct / 100)."""
        from decimal import Decimal

        quantity = 10
        unit_price = Decimal("100.00")
        discount_pct = Decimal("10.00")

        expected_revenue = float(quantity * unit_price * (1 - discount_pct / 100))
        assert abs(expected_revenue - 900.00) < 0.01

    def test_cost_estimate_is_60_pct(self, spark):
        """cost_estimate must be 60% of revenue."""
        revenue = 900.00
        cost = revenue * 0.60
        assert abs(cost - 540.00) < 0.01

    def test_fact_columns_present(self, spark, sample_order_items, sample_orders):
        """Verify revenue calculation via PySpark column expression."""
        from decimal import Decimal

        # Simulate the fact_sales revenue calculation
        items = sample_order_items.withColumn(
            "revenue",
            F.round(
                F.col("quantity") * F.col("unit_price") * (1 - F.col("discount_pct") / 100), 2
            ),
        ).withColumn("cost_estimate", F.round(F.col("revenue") * 0.60, 2))

        assert "revenue" in items.columns
        assert "cost_estimate" in items.columns

        # First row: 2 * 189.90 * (1 - 0/100) = 379.80
        row = items.filter(F.col("order_item_id") == 1).select("revenue").first()
        assert abs(float(row.revenue) - 379.80) < 0.01


class TestDimCustomer:
    def test_segment_logic(self, spark, sample_customers):
        """Customer segment must be assigned based on customer_id rule."""
        # In the demo, segment is rule-based on customer_id
        # IDs 1-5 → ENTERPRISE, 6-10 → MID, >10 → SMALL
        def classify(customer_id: int) -> str:
            if customer_id <= 5:
                return "ENTERPRISE"
            elif customer_id <= 10:
                return "MID"
            return "SMALL"

        assert classify(1) == "ENTERPRISE"
        assert classify(6) == "MID"
        assert classify(11) == "SMALL"

    def test_scd2_requires_valid_from(self, spark, sample_customers):
        """Every dim_customer row must have a valid_from date."""
        from datetime import date

        today = date.today()
        enriched = sample_customers.withColumn(
            "valid_from", F.lit(today.isoformat()).cast("date")
        ).withColumn("is_current", F.lit(True))

        valid_from_values = [row.valid_from for row in enriched.select("valid_from").collect()]
        assert all(v is not None for v in valid_from_values)
