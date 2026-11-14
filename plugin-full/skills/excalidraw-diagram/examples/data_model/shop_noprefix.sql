-- The same kind of shop with no dim_/fact_ prefixes: roles must come from structure alone.
CREATE TABLE calendar (
    date_key   integer PRIMARY KEY,
    full_date  date NOT NULL,
    year       smallint NOT NULL,
    month      smallint NOT NULL,
    day_name   varchar(12) NOT NULL
);

CREATE TABLE customers (
    customer_key serial PRIMARY KEY,
    full_name    varchar(120) NOT NULL,
    city         varchar(80),
    segment      varchar(40)
);

CREATE TABLE products (
    product_key  serial PRIMARY KEY,
    product_name varchar(120) NOT NULL,
    brand        varchar(80),
    list_price   numeric(10, 2)
);

CREATE TABLE promotions (
    promotion_key serial PRIMARY KEY,
    promo_name    varchar(80) NOT NULL,
    channel       varchar(40)
);

-- many-to-many between products and promotions: keys only
CREATE TABLE product_promotion (
    product_key   integer NOT NULL REFERENCES products (product_key),
    promotion_key integer NOT NULL REFERENCES promotions (promotion_key),
    PRIMARY KEY (product_key, promotion_key)
);

CREATE TABLE sales (
    sale_key     bigserial PRIMARY KEY,
    date_key     integer NOT NULL REFERENCES calendar (date_key),
    customer_key integer NOT NULL REFERENCES customers (customer_key),
    product_key  integer NOT NULL REFERENCES products (product_key),
    quantity     integer NOT NULL,
    net_amount   numeric(12, 2) NOT NULL,
    discount     numeric(12, 2)
);
