with customers as (select * from {{ ref('stg_customers') }}),
orders as (select * from {{ ref('stg_orders') }}),
payments as (select * from {{ ref('stg_payments') }})
select customers.customer_id, customers.first_name, customers.last_name,
       min(orders.order_date) as first_order,
       count(orders.order_id) as number_of_orders,
       sum(payments.amount) as customer_lifetime_value
from customers
left join orders using (customer_id)
left join payments using (order_id)
group by 1, 2, 3
