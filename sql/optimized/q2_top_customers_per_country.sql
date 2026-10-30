-- Q2 optimised: filter orders first (projection only), pre-aggregate lines to ORDER grain (shrinks the join
-- input ~3x), then join to the small customer dimension and rank.
WITH order_rev AS (
  SELECT order_id, SUM(line_total) AS rev FROM order_items GROUP BY order_id
), cust_rev AS (
  SELECT o.customer_id, SUM(r.rev) AS revenue
  FROM orders o JOIN order_rev r ON r.order_id = o.order_id
  WHERE o.status = 'completed'
  GROUP BY o.customer_id
)
SELECT country, customer_id, revenue FROM (
  SELECT c.country, c.customer_id, cr.revenue,
         ROW_NUMBER() OVER (PARTITION BY c.country ORDER BY cr.revenue DESC, c.customer_id) AS rk
  FROM cust_rev cr JOIN customers c ON c.customer_id = cr.customer_id
) WHERE rk <= 3 ORDER BY country, rk;
