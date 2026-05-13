-- ============================================================
-- OLTP Schema: B2B E-Commerce (3rd Normal Form)
-- Target: Azure SQL Database (serverless)
-- ============================================================

-- Each table is in 3NF:
--   1NF: atomic values, no repeating groups
--   2NF: every non-key column depends on the whole PK
--   3NF: no transitive dependencies (e.g. city/country in addresses,
--         not duplicated in customers or suppliers)

CREATE SCHEMA IF NOT EXISTS oltp;
GO

-- ------------------------------------------------------------
-- addresses  (shared by customers and suppliers)
-- ------------------------------------------------------------
CREATE TABLE oltp.addresses (
    address_id   INT           IDENTITY(1,1) PRIMARY KEY,
    street       NVARCHAR(200) NOT NULL,
    city         NVARCHAR(100) NOT NULL,
    zip          NVARCHAR(20)  NOT NULL,
    country_code CHAR(2)       NOT NULL  -- ISO 3166-1 alpha-2
);

-- ------------------------------------------------------------
-- categories  (self-referencing hierarchy: top-level → sub)
-- ------------------------------------------------------------
CREATE TABLE oltp.categories (
    category_id        INT           IDENTITY(1,1) PRIMARY KEY,
    name               NVARCHAR(100) NOT NULL,
    parent_category_id INT           NULL
        REFERENCES oltp.categories(category_id)
);

-- ------------------------------------------------------------
-- suppliers
-- ------------------------------------------------------------
CREATE TABLE oltp.suppliers (
    supplier_id   INT           IDENTITY(1,1) PRIMARY KEY,
    name          NVARCHAR(200) NOT NULL,
    contact_email NVARCHAR(200) NULL,
    address_id    INT           NOT NULL
        REFERENCES oltp.addresses(address_id),
    created_at    DATETIME2     NOT NULL DEFAULT GETUTCDATE()
);

-- ------------------------------------------------------------
-- customers  (B2B: company accounts)
-- ------------------------------------------------------------
CREATE TABLE oltp.customers (
    customer_id INT           IDENTITY(1,1) PRIMARY KEY,
    name        NVARCHAR(200) NOT NULL,   -- contact person name
    email       NVARCHAR(200) NOT NULL UNIQUE,
    company     NVARCHAR(200) NOT NULL,
    address_id  INT           NOT NULL
        REFERENCES oltp.addresses(address_id),
    created_at  DATETIME2     NOT NULL DEFAULT GETUTCDATE()
);

-- ------------------------------------------------------------
-- products
-- ------------------------------------------------------------
CREATE TABLE oltp.products (
    product_id  INT             IDENTITY(1,1) PRIMARY KEY,
    sku         NVARCHAR(50)    NOT NULL UNIQUE,
    name        NVARCHAR(300)   NOT NULL,
    description NVARCHAR(MAX)   NULL,
    category_id INT             NULL
        REFERENCES oltp.categories(category_id),
    supplier_id INT             NOT NULL
        REFERENCES oltp.suppliers(supplier_id),
    list_price  DECIMAL(10, 2)  NOT NULL CHECK (list_price >= 0),
    stock_qty   INT             NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    weight_kg   DECIMAL(8, 3)   NULL,
    created_at  DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    updated_at  DATETIME2       NOT NULL DEFAULT GETUTCDATE()
);

-- ------------------------------------------------------------
-- orders
-- ------------------------------------------------------------
CREATE TABLE oltp.orders (
    order_id            INT          IDENTITY(1,1) PRIMARY KEY,
    customer_id         INT          NOT NULL
        REFERENCES oltp.customers(customer_id),
    order_date          DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
    status              NVARCHAR(30) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CONFIRMED', 'SHIPPED', 'DELIVERED', 'CANCELLED')),
    shipping_address_id INT          NOT NULL
        REFERENCES oltp.addresses(address_id),
    created_at          DATETIME2    NOT NULL DEFAULT GETUTCDATE()
);

-- ------------------------------------------------------------
-- order_items  (line items; unit_price snapshot at order time)
-- ------------------------------------------------------------
CREATE TABLE oltp.order_items (
    order_item_id INT            IDENTITY(1,1) PRIMARY KEY,
    order_id      INT            NOT NULL
        REFERENCES oltp.orders(order_id),
    product_id    INT            NOT NULL
        REFERENCES oltp.products(product_id),
    quantity      INT            NOT NULL CHECK (quantity > 0),
    unit_price    DECIMAL(10, 2) NOT NULL CHECK (unit_price >= 0),
    discount_pct  DECIMAL(5, 2)  NOT NULL DEFAULT 0
        CHECK (discount_pct BETWEEN 0 AND 100)
);
GO

-- ------------------------------------------------------------
-- Indexes for common ETL watermark queries
-- ------------------------------------------------------------
CREATE INDEX ix_orders_order_date      ON oltp.orders(order_date);
CREATE INDEX ix_products_updated_at    ON oltp.products(updated_at);
CREATE INDEX ix_customers_created_at   ON oltp.customers(created_at);
