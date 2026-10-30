-- Q2: top 3 customers per country by completed revenue.
-- Inefficiencies: joins the full wide tables (SELECT *) before filtering/aggregating, aggregates at customer
-- grain after a 3-way row-multiplying join, filter applied late.
SELECT country, customer_id, revenue FROM (
  SELECT c.country, c.customer_id, SUM(i.quantity * i.unit_price) AS revenue,
         ROW_NUMBER() OVER (PARTITION BY c.country ORDER BY SUM(i.quantity * i.unit_price) DESC, c.customer_id) AS rk
  FROM (SELECT * FROM customers) c
  JOIN (SELECT * FROM orders) o ON o.customer_id = c.customer_id
  JOIN (SELECT * FROM order_items) i ON i.order_id = o.order_id
  WHERE lower(o.status) = 'completed'
  GROUP BY c.country, c.customer_id
) WHERE rk <= 3 ORDER BY country, rk;
