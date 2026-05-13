-- ============================================================
-- Star Schema Reference DDL (Kimball / Gold Layer)
-- These tables are created and managed by PySpark/Delta Lake.
-- This file serves as documentation / reference for the structure.
-- In production: tables live in ADLS Gen2 as Delta tables,
-- surfaced via Databricks Unity Catalog.
-- ============================================================

-- ------------------------------------------------------------
-- dim_date  (static, generated once for 2020–2030)
-- ------------------------------------------------------------
-- date_key:     YYYYMMDD integer surrogate key (e.g. 20240115)
-- date:         calendar date
-- year/quarter/month/week: extracted components
-- is_weekend:   Saturday or Sunday
-- is_holiday_de: public holiday in Germany (major ones)
CREATE TABLE gold.dim_date (
    date_key     INT          NOT NULL PRIMARY KEY,
    date         DATE         NOT NULL,
    year         SMALLINT     NOT NULL,
    quarter      TINYINT      NOT NULL,
    month        TINYINT      NOT NULL,
    month_name   VARCHAR(10)  NOT NULL,
    week         TINYINT      NOT NULL,
    day_of_week  TINYINT      NOT NULL,   -- 1=Mon … 7=Sun (ISO)
    day_name     VARCHAR(10)  NOT NULL,
    is_weekend   BIT          NOT NULL,
    is_holiday_de BIT         NOT NULL
);

-- ------------------------------------------------------------
-- dim_customer  (SCD Type 2 — slowly changing dimension)
-- SCD2 means: when a customer's company or address changes,
-- we DON'T overwrite the old row. Instead, we:
--   1. Set valid_to = today-1 and is_current = FALSE on the old row
--   2. Insert a new row with valid_from = today, is_current = TRUE
-- This lets fact rows keep their historical snapshot intact.
-- ------------------------------------------------------------
CREATE TABLE gold.dim_customer (
    customer_key     BIGINT       NOT NULL PRIMARY KEY,  -- surrogate
    customer_id      INT          NOT NULL,              -- natural key (from OLTP)
    name             NVARCHAR(200) NOT NULL,
    email            NVARCHAR(200) NOT NULL,
    company          NVARCHAR(200) NOT NULL,
    city             NVARCHAR(100) NOT NULL,
    country_code     CHAR(2)      NOT NULL,
    customer_segment NVARCHAR(50) NOT NULL,  -- 'SMALL', 'MID', 'ENTERPRISE'
    valid_from       DATE         NOT NULL,
    valid_to         DATE         NULL,       -- NULL means currently active
    is_current       BIT          NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------
-- dim_product  (SCD Type 1 — overwrite, plus embedding vector)
-- SCD1: price changes are simply overwritten (no history kept).
-- embedding_vector: 1536 floats from text-embedding-ada-002.
--   Stored as VARBINARY in SQL reference, but as ARRAY<FLOAT>
--   in the actual Delta Lake table.
-- ------------------------------------------------------------
CREATE TABLE gold.dim_product (
    product_key      BIGINT          NOT NULL PRIMARY KEY,
    product_id       INT             NOT NULL,
    sku              NVARCHAR(50)    NOT NULL,
    name             NVARCHAR(300)   NOT NULL,
    category         NVARCHAR(100)   NULL,
    subcategory      NVARCHAR(100)   NULL,
    supplier_name    NVARCHAR(200)   NULL,
    list_price       DECIMAL(10,2)   NOT NULL,
    weight_kg        DECIMAL(8,3)    NULL,
    categorized_by   NVARCHAR(20)    NOT NULL DEFAULT 'manual'  -- 'manual' | 'llm'
    -- embedding_vector: in Delta Lake → ARRAY<FLOAT> (1536 dims)
);

-- ------------------------------------------------------------
-- dim_supplier  (SCD Type 1)
-- ------------------------------------------------------------
CREATE TABLE gold.dim_supplier (
    supplier_key  BIGINT        NOT NULL PRIMARY KEY,
    supplier_id   INT           NOT NULL,
    name          NVARCHAR(200) NOT NULL,
    country_code  CHAR(2)       NOT NULL
);

-- ------------------------------------------------------------
-- fact_sales  (grain: one order line item)
-- Revenue is calculated as: quantity * unit_price * (1 - discount_pct/100)
-- cost_estimate: 60% of list_price (placeholder — no cost data in OLTP)
-- ------------------------------------------------------------
CREATE TABLE gold.fact_sales (
    order_item_key  BIGINT          NOT NULL PRIMARY KEY,   -- surrogate
    order_item_id   INT             NOT NULL,               -- natural key
    order_key       INT             NOT NULL,               -- from OLTP
    customer_key    BIGINT          NOT NULL REFERENCES gold.dim_customer(customer_key),
    product_key     BIGINT          NOT NULL REFERENCES gold.dim_product(product_key),
    date_key        INT             NOT NULL REFERENCES gold.dim_date(date_key),
    supplier_key    BIGINT          NOT NULL REFERENCES gold.dim_supplier(supplier_key),
    order_status    NVARCHAR(30)    NOT NULL,
    quantity        INT             NOT NULL,
    unit_price      DECIMAL(10,2)   NOT NULL,
    discount_pct    DECIMAL(5,2)    NOT NULL,
    revenue         DECIMAL(12,2)   NOT NULL,               -- quantity * unit_price * (1 - discount_pct/100)
    cost_estimate   DECIMAL(12,2)   NOT NULL,               -- revenue * 0.60
    ingested_at     DATETIME2       NOT NULL
);

-- ============================================================
-- Useful Analytical Queries (examples for SQL Warehouse)
-- ============================================================

-- Monthly revenue by customer segment
SELECT
    d.year,
    d.month_name,
    c.customer_segment,
    SUM(f.revenue)   AS total_revenue,
    COUNT(DISTINCT f.order_key) AS order_count
FROM gold.fact_sales f
JOIN gold.dim_date     d ON f.date_key    = d.date_key
JOIN gold.dim_customer c ON f.customer_key = c.customer_key
WHERE c.is_current = 1
GROUP BY d.year, d.month, d.month_name, c.customer_segment
ORDER BY d.year, d.month, c.customer_segment;

-- Top 10 products by revenue YTD
SELECT TOP 10
    p.name,
    p.category,
    SUM(f.revenue)   AS ytd_revenue,
    SUM(f.quantity)  AS ytd_units
FROM gold.fact_sales f
JOIN gold.dim_product p ON f.product_key = p.product_key
JOIN gold.dim_date    d ON f.date_key    = d.date_key
WHERE d.year = YEAR(GETDATE())
GROUP BY p.product_key, p.name, p.category
ORDER BY ytd_revenue DESC;

-- Supplier contribution to gross margin
SELECT
    s.name AS supplier,
    SUM(f.revenue)       AS revenue,
    SUM(f.cost_estimate) AS cost,
    SUM(f.revenue - f.cost_estimate) AS gross_margin,
    ROUND(100.0 * SUM(f.revenue - f.cost_estimate) / NULLIF(SUM(f.revenue),0), 1) AS margin_pct
FROM gold.fact_sales f
JOIN gold.dim_supplier s ON f.supplier_key = s.supplier_key
GROUP BY s.supplier_key, s.name
ORDER BY gross_margin DESC;
