-- The same shop with every planted issue fixed: the review must stay silent on it.
CREATE TABLE dim_date (
    date_key     integer PRIMARY KEY,
    full_date    date NOT NULL,
    year         smallint NOT NULL,
    month        smallint NOT NULL,
    day_name     varchar(12) NOT NULL
);

CREATE TABLE dim_customer (
    customer_key serial PRIMARY KEY,
    customer_id  varchar(20) NOT NULL,
    full_name    varchar(120) NOT NULL,
    city         varchar(80),
    address      varchar(200),
    valid_from   date NOT NULL,
    valid_to     date,
    is_current   boolean NOT NULL
);

CREATE TABLE dim_product (
    product_key   serial PRIMARY KEY,
    product_id    integer NOT NULL,
    product_name  varchar(120) NOT NULL,
    brand         varchar(80),
    category_name varchar(80) NOT NULL
);

CREATE TABLE fact_order_line (
    order_line_key bigserial PRIMARY KEY,
    date_key       integer NOT NULL REFERENCES dim_date (date_key),
    customer_key   integer NOT NULL REFERENCES dim_customer (customer_key),
    product_key    integer NOT NULL REFERENCES dim_product (product_key),
    quantity       integer NOT NULL,
    unit_price     numeric(10, 2) NOT NULL,
    line_amount    numeric(12, 2) NOT NULL
);

CREATE TABLE fact_payment (
    payment_key  bigserial PRIMARY KEY,
    date_key     integer NOT NULL,
    customer_key integer NOT NULL,
    amount       numeric(12, 2) NOT NULL
);
ALTER TABLE fact_payment ADD CONSTRAINT fk_pay_date FOREIGN KEY (date_key) REFERENCES dim_date (date_key);
ALTER TABLE fact_payment ADD CONSTRAINT fk_pay_cust FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key);
