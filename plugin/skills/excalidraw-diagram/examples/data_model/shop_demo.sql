-- Online shop, 6 tables. Issues planted on purpose (see each table).
CREATE TABLE dim_date (
    date_key     integer PRIMARY KEY,
    full_date    date NOT NULL,
    year         smallint NOT NULL,
    month        smallint NOT NULL,
    day_name     varchar(12) NOT NULL
);

-- planted: the address changes over time but there is no valid_from / valid_to (SCD2)
CREATE TABLE dim_customer (
    customer_key serial PRIMARY KEY,
    customer_id  varchar(20) NOT NULL,
    full_name    varchar(120) NOT NULL,
    city         varchar(80),
    address      varchar(200)
);

-- planted: unnecessary snowflake of dim_product, could be denormalized
CREATE TABLE dim_category (
    category_key  serial PRIMARY KEY,
    category_name varchar(80) NOT NULL
);

-- planted: keyed by the source system's id, no surrogate key
CREATE TABLE dim_product (
    product_id    integer PRIMARY KEY,
    product_name  varchar(120) NOT NULL,
    brand         varchar(80),
    category_key  integer REFERENCES dim_category (category_key)
);

-- grain: one row per order line
CREATE TABLE fact_order_line (
    order_line_key bigserial PRIMARY KEY,
    date_key       integer NOT NULL REFERENCES dim_date (date_key),
    customer_key   integer NOT NULL REFERENCES dim_customer (customer_key),
    product_id     integer NOT NULL REFERENCES dim_product (product_id),
    quantity       integer NOT NULL,
    unit_price     numeric(10, 2) NOT NULL,
    line_amount    numeric(12, 2) NOT NULL
);

-- planted: the foreign key points at a table that does not exist
CREATE TABLE stg_payments (
    payment_id integer PRIMARY KEY,
    order_id   integer NOT NULL REFERENCES orders (order_id),
    amount     numeric(12, 2),
    paid_at    timestamp
);
