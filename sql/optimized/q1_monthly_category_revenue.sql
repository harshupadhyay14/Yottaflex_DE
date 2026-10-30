-- Q1 optimised: read the small pre-aggregated daily rollup (built at publish time) with a sargable range filter.
SELECT strftime(order_date, '%Y-%m') AS month, category, SUM(revenue) AS revenue
FROM agg_daily_category_revenue
WHERE order_date >= DATE '2025-01-01' AND order_date < DATE '2026-01-01'
GROUP BY 1, 2
ORDER BY 1, 2;
