-- Q3 optimised: sargable timestamp range + NOT EXISTS anti-join, only the key column is read.
SELECT c.customer_id FROM customers c
WHERE NOT EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id AND o.order_ts >= TIMESTAMP '2025-10-01')
ORDER BY c.customer_id;
