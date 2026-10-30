-- Q3: customers with no order in Q4 2025 (>= 2025-10-01).
-- Inefficiencies: NOT IN over a non-sargable function filter on orders; SELECT * from customers.
SELECT customer_id FROM (SELECT * FROM customers)
WHERE customer_id NOT IN (SELECT customer_id FROM orders WHERE strftime(order_ts, '%Y-%m') >= '2025-10')
ORDER BY customer_id;
