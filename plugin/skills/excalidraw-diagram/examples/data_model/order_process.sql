-- An order process modelled from the business description, before running the tool.
-- No dim_/fact_ prefixes on purpose: roles must come from structure.

CREATE TABLE calendar (
    date_key  integer PRIMARY KEY,
    full_date date NOT NULL,
    year      smallint NOT NULL,
    month     smallint NOT NULL,
    day_name  varchar(12) NOT NULL
);

-- the address and segment change over time: keep every version (SCD type 2)
CREATE TABLE customer (
    customer_key serial PRIMARY KEY,
    customer_id  varchar(20) NOT NULL,
    full_name    varchar(120) NOT NULL,
    city         varchar(80),
    address      varchar(200),
    valid_from   date NOT NULL,
    valid_to     date,
    is_current   boolean NOT NULL
);

-- product -> product_category -> department: a three-level snowflake
CREATE TABLE department (
    department_key  serial PRIMARY KEY,
    department_name varchar(80) NOT NULL
);
CREATE TABLE product_category (
    category_key   serial PRIMARY KEY,
    category_name  varchar(80) NOT NULL,
    department_key integer REFERENCES department (department_key)
);
CREATE TABLE product (
    product_key  serial PRIMARY KEY,
    sku          varchar(30) NOT NULL,
    product_name varchar(120) NOT NULL,
    brand        varchar(80),
    category_key integer REFERENCES product_category (category_key)
);

-- planted: keyed by the warehouse's own code, not a surrogate
CREATE TABLE warehouse (
    warehouse_code varchar(10) PRIMARY KEY,
    warehouse_name varchar(80) NOT NULL,
    country        varchar(60)
);

CREATE TABLE promotion (
    promotion_key  serial PRIMARY KEY,
    promotion_name varchar(80) NOT NULL,
    channel        varchar(40)
);

CREATE TABLE segment (
    segment_key  serial PRIMARY KEY,
    segment_name varchar(60) NOT NULL
);

-- grain: one order line. order_number is a degenerate dimension (it lives in the fact).
CREATE TABLE order_line (
    order_line_key bigserial PRIMARY KEY,
    order_number   varchar(20) NOT NULL,
    customer_key   integer NOT NULL REFERENCES customer (customer_key),
    product_key    integer NOT NULL REFERENCES product (product_key),
    order_date_key integer NOT NULL REFERENCES calendar (date_key),
    quantity       integer NOT NULL,
    unit_price     numeric(10, 2) NOT NULL,
    net_amount     numeric(12, 2) NOT NULL
);

-- accumulating snapshot: one row per order, updated as it moves; three role-playing dates
CREATE TABLE order_fulfilment (
    fulfilment_key    bigserial PRIMARY KEY,
    order_number      varchar(20) NOT NULL,
    customer_key      integer NOT NULL REFERENCES customer (customer_key),
    order_date_key    integer NOT NULL REFERENCES calendar (date_key),
    ship_date_key     integer REFERENCES calendar (date_key),
    delivery_date_key integer REFERENCES calendar (date_key),
    days_to_ship      integer,
    days_to_deliver   integer
);

-- periodic snapshot: stock on hand per product, warehouse and day
CREATE TABLE inventory_snapshot (
    snapshot_key     bigserial PRIMARY KEY,
    date_key         integer NOT NULL REFERENCES calendar (date_key),
    product_key      integer NOT NULL REFERENCES product (product_key),
    warehouse_code   varchar(10) NOT NULL REFERENCES warehouse (warehouse_code),
    quantity_on_hand integer NOT NULL
);

-- many-to-many between customers and segments: keys only
CREATE TABLE customer_segment (
    customer_key integer NOT NULL REFERENCES customer (customer_key),
    segment_key  integer NOT NULL REFERENCES segment (segment_key),
    PRIMARY KEY (customer_key, segment_key)
);

-- factless: which product was on which promotion on which day; nothing to measure
CREATE TABLE promotion_coverage (
    product_key   integer NOT NULL REFERENCES product (product_key),
    promotion_key integer NOT NULL REFERENCES promotion (promotion_key),
    date_key      integer NOT NULL REFERENCES calendar (date_key),
    PRIMARY KEY (product_key, promotion_key, date_key)
);
