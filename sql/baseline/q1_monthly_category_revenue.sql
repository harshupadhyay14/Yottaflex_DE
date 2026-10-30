-- Q1: completed revenue by month and category, 2025.
-- Inefficiencies: SELECT * subqueries (no column pruning), non-sargable function-wrapped filters
-- (strftime/lower on columns), revenue recomputed from raw lines on every run.
SELECT strftime(o.order_ts, '%Y-%m') AS month, p.category, SUM(i.quantity * i.unit_price) AS revenue
FROM (SELECT * FROM orders) o
JOIN (SELECT * FROM order_items) i ON i.order_id = o.order_id
JOIN (SELECT * FROM products) p ON p.product_id = i.product_id
WHERE strftime(o.order_ts, '%Y') = '2025' AND lower(o.status) = 'completed'
GROUP BY 1, 2
ORDER BY 1, 2;
