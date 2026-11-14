-- one row per customer, renamed from the raw table
select id as customer_id, first_name, last_name
from {{ source('raw', 'customers') }}
