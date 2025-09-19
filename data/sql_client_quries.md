# Sql quries of each user query

### 1. what is the purchase history of coca cola 1.5 liter i.e the last four orders.?
 Since coca cola is not listed in the product description so using WALLS MAGNUM CHILL instead.

```sql 
SELECT TOP 4
    po.ord_number AS OrderNumber,
    po.ord_date AS OrderDate,
    s.sup_name AS SupplierName,
    p.prd_description AS Product,
    pol.orl_qtyord AS QuantityOrdered,
    pol.orl_qtydel AS QuantityDelivered,
    pol.orl_cost AS UnitCost,
    (pol.orl_qtydel * pol.orl_cost) AS TotalCost
FROM dbo.Products p
JOIN dbo.SupplierProducts sp ON sp.spr_prdfk = p.prd_pk
JOIN dbo.PurchaseOrderlines pol ON pol.orl_sprfk = sp.spr_pk
JOIN dbo.PurchaseOrders po ON po.ord_pk = pol.orl_ordfk
JOIN dbo.Suppliers s ON s.sup_pk = sp.spr_supfk
WHERE p.prd_description LIKE '%Coca Cola 1.5%'
ORDER BY po.ord_date DESC; 
```


### 2. which is the slowest selling product this week.?
Using last year instead of last week because dataset is limmited to year.
```sql
SELECT TOP 1
    p.prd_description AS Product,
    SUM(ps.psa_quantity) AS TotalQuantitySold,
    SUM(ps.psa_value) AS TotalSalesValue
FROM dbo.ProductSales ps
JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE()) --- you can change the date here
GROUP BY p.prd_description
ORDER BY SUM(ps.psa_quantity) ASC; 
```


### 3. what is the growest margin this week.?
Using year instead of week because dataset is limited to last year.
```sql
SELECT TOP 1
    p.prd_description AS Product,
    SUM(ps.psa_value) AS TotalSales,
    SUM(ps.psa_cost) AS TotalCost,
    (SUM(ps.psa_value) - SUM(ps.psa_cost)) AS GrossMargin,
    CAST(
        (SUM(ps.psa_value) - SUM(ps.psa_cost)) * 100.0 / NULLIF(SUM(ps.psa_value), 0)
        AS DECIMAL(10,2)
    ) AS GrossMarginPercent
FROM dbo.ProductSales ps
JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE())
GROUP BY p.prd_description
ORDER BY GrossMargin DESC;
```


### 4. what is the gorwest margin this month.?
Using year instead of month because dataset is limited to last year.

```sql
SELECT TOP 1
    p.prd_description AS Product,
    SUM(ps.psa_value) AS TotalSales,
    SUM(ps.psa_cost) AS TotalCost,
    (SUM(ps.psa_value) - SUM(ps.psa_cost)) AS GrossMargin,
    CAST(
        (SUM(ps.psa_value) - SUM(ps.psa_cost)) * 100.0 / NULLIF(SUM(ps.psa_value), 0)
        AS DECIMAL(10,2)
    ) AS GrossMarginPercent
FROM dbo.ProductSales ps
JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE()) ---change the date here
GROUP BY p.prd_description
ORDER BY GrossMargin DESC;
```


5. ### What is the number of products bought in an average basket?

```sql
SELECT 
    CAST(SUM(td.trd_quantity) * 1.0 / COUNT(DISTINCT th.trh_pk) AS DECIMAL(10,2)) AS AvgBasketSize
FROM dbo.TillTransactionHeaders th
JOIN dbo.TillTransactionDetails td 
    ON td.trd_trhfk = th.trh_pk
WHERE th.trh_date >= DATEADD(YEAR, -1, GETDATE()); 
```


6. ### What is the average basket spent today?
The data in database is limited to last year so right now this query returns null.

```sql
 SELECT 
    CAST(SUM(td.trd_net) * 1.0 / COUNT(DISTINCT th.trh_pk) AS DECIMAL(10,2)) AS AvgBasketSpend
FROM dbo.TillTransactionHeaders th
JOIN dbo.TillTransactionDetails td 
    ON td.trd_trhfk = th.trh_pk
WHERE CAST(th.trh_date AS DATE) = CAST(GETDATE() AS DATE); 
```


7. ### What is this month's total sale?
Using year instead of month because dataset is limited to last year.

```sql
 SELECT 
    CAST(SUM(td.trd_net) AS DECIMAL(18,2)) AS TotalSalesThisMonth
FROM dbo.TillTransactionHeaders th
JOIN dbo.TillTransactionDetails td 
    ON td.trd_trhfk = th.trh_pk
WHERE YEAR(th.trh_date) = YEAR(GETDATE())
  AND MONTH(th.trh_date) = MONTH(GETDATE()); 
  ```


8. ### What are the lowest margin products that are not Cigarette and that are not in promotion.?

```sql
SELECT TOP 10
    p.prd_description AS Product,
    SUM(ps.psa_value) AS TotalSales,
    SUM(ps.psa_cost) AS TotalCost,
    (SUM(ps.psa_value) - SUM(ps.psa_cost)) AS GrossMargin,
    CAST(
        (SUM(ps.psa_value) - SUM(ps.psa_cost)) * 100.0 / NULLIF(SUM(ps.psa_value), 0)
        AS DECIMAL(10,2)
    ) AS GrossMarginPercent
FROM dbo.ProductSales ps
JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
LEFT JOIN dbo.Barcodes b ON b.bar_prdfk = p.prd_pk
LEFT JOIN dbo.PromotionPrices prm ON prm.prm_prdfk = p.prd_pk
LEFT JOIN dbo.PromotionCosts pc ON pc.pcs_sprfk IN (
    SELECT spr_pk FROM dbo.SupplierProducts sp WHERE sp.spr_prdfk = p.prd_pk
)
WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE())
  AND (b.bar_cigPLU IS NULL OR b.bar_cigPLU = '')       -- Exclude cigarettes
  AND prm.prm_pk IS NULL                                -- Exclude promotion prices
  AND pc.pcs_pk IS NULL                                 -- Exclude promotion costs
GROUP BY p.prd_description
ORDER BY GrossMarginPercent ASC;
```


9. ### What are my live Sales now that is a total amount to sale all the products.?
Due to un availablity of data this retruns null.

```sql
 SELECT 
    CAST(SUM(td.trd_net) AS DECIMAL(18,2)) AS LiveSalesTotal
FROM dbo.TillTransactionDetails td
JOIN dbo.TillTransactionHeaders th 
    ON th.trh_pk = td.trd_trhfk
WHERE CAST(th.trh_date AS DATE) = CAST(GETDATE() AS DATE); 
```
To retrieve record change current date to some past data. e.g replace CAST(th.trh_date AS DATE) = '2025-09-17';


10. ### How many products were refunded this week?
Using year instead of week because dataset is limited to last year.

```sql
 SELECT 
    ABS(SUM(td.trd_quantity)) AS RefundedProducts
FROM dbo.TillTransactionDetails td
JOIN dbo.TillTransactionHeaders th 
    ON th.trh_pk = td.trd_trhfk
WHERE td.trd_quantity < 0
  AND th.trh_date >= DATEADD(YEAR, -1, GETDATE());
  ```


11. ### How many products were refunded today?
 Retuns Null since no product is refunded today

```sql
SELECT 
    ABS(SUM(td.trd_quantity)) AS RefundedProductsToday
FROM dbo.TillTransactionDetails td
JOIN dbo.TillTransactionHeaders th 
    ON th.trh_pk = td.trd_trhfk
WHERE td.trd_quantity < 0
  AND CAST(th.trh_date AS DATE) = CAST(GETDATE() AS DATE);
  ```


12. ### Which product is selling under the recommended selling price from its supplier?

```sql
 SELECT 
    p.prd_description AS Product,
    b.bar_barcode AS Barcode,
    prc.prc_price AS StorePrice,
    ch.csh_sellprice AS SupplierRecommendedPrice,
    (ch.csh_sellprice - prc.prc_price) AS PriceDifference
FROM dbo.Products p
JOIN dbo.Barcodes b 
    ON b.bar_prdfk = p.prd_pk
JOIN dbo.Prices prc 
    ON prc.prc_barfk = b.bar_pk
JOIN dbo.CostpricesHistory ch 
    ON ch.csh_prdfk = p.prd_pk
WHERE prc.prc_price < ch.csh_sellprice; 
```


13. ### Which product that were on promotion that did not sell and the sales value is lesser than the normal sale value was on promotion?

```sql
 WITH PromoSales AS (
    SELECT 
        p.prd_pk,
        p.prd_description,
        SUM(ps.psa_value) AS PromoSalesValue
    FROM dbo.ProductSales ps
    JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
    JOIN dbo.PromotionPrices prm 
        ON prm.prm_prdfk = ps.psa_prdfk
       AND ps.psa_date BETWEEN prm.prm_effective AND prm.prm_expires
    GROUP BY p.prd_pk, p.prd_description
),
NormalSales AS (
    SELECT 
        p.prd_pk,
        SUM(ps.psa_value) AS NormalSalesValue
    FROM dbo.ProductSales ps
    JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
    LEFT JOIN dbo.PromotionPrices prm 
        ON prm.prm_prdfk = ps.psa_prdfk
       AND ps.psa_date BETWEEN prm.prm_effective AND prm.prm_expires
    WHERE prm.prm_pk IS NULL  -- sales not during promotion
    GROUP BY p.prd_pk
)
SELECT 
    pr.prd_description AS Product,
    ps.PromoSalesValue,
    ns.NormalSalesValue
FROM PromoSales ps
JOIN NormalSales ns ON ns.prd_pk = ps.prd_pk
JOIN dbo.Products pr ON pr.prd_pk = ps.prd_pk
WHERE ps.PromoSalesValue < ns.NormalSalesValue
ORDER BY (ns.NormalSalesValue - ps.PromoSalesValue) DESC;
 ```


14. ### Which product increased in sales while it was on promotion?

```sql
 WITH PromoSales AS (
    SELECT 
        p.prd_pk,
        p.prd_description,
        SUM(ps.psa_quantity) AS UnitsOnPromo
    FROM dbo.ProductSales ps
    JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
    JOIN dbo.PromotionPrices prm 
        ON prm.prm_prdfk = ps.psa_prdfk
       AND ps.psa_date BETWEEN prm.prm_effective AND prm.prm_expires
    GROUP BY p.prd_pk, p.prd_description
),
NormalSales AS (
    SELECT 
        p.prd_pk,
        SUM(ps.psa_quantity) AS UnitsNormal
    FROM dbo.ProductSales ps
    JOIN dbo.Products p ON p.prd_pk = ps.psa_prdfk
    LEFT JOIN dbo.PromotionPrices prm 
        ON prm.prm_prdfk = ps.psa_prdfk
       AND ps.psa_date BETWEEN prm.prm_effective AND prm.prm_expires
    WHERE prm.prm_pk IS NULL
    GROUP BY p.prd_pk
)
SELECT 
    pr.prd_description AS Product,
    ps.UnitsOnPromo AS UnitSoldOnPromo,
    ns.UnitsNormal AS UnitSoldNormal
FROM PromoSales ps
JOIN NormalSales ns ON ns.prd_pk = ps.prd_pk
JOIN dbo.Products pr ON pr.prd_pk = ps.prd_pk
WHERE ps.UnitsOnPromo > ns.UnitsNormal
ORDER BY (ps.UnitsOnPromo - ns.UnitsNormal) DESC;
 ```


15. ### Which product in my stock have not been sold in the last six week but I've purchase them in last six weeks?
using year here to get the records.
```sql
 WITH Purchased AS (
    SELECT 
        st.stk_prdfk AS ProductID,
        SUM(st.stk_quantity) AS PurchasedQty
    FROM dbo.StockTransactions st
    WHERE st.stk_date >= DATEADD(YEAR, -1, GETDATE())
      AND st.stk_quantity > 0   -- purchased
    GROUP BY st.stk_prdfk
),
Sold AS (
    SELECT 
        ps.psa_prdfk AS ProductID,
        SUM(ps.psa_quantity) AS SoldQty
    FROM dbo.ProductSales ps
    WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE())
    GROUP BY ps.psa_prdfk
)
SELECT 
    p.prd_description AS Product,
    pu.PurchasedQty,
    ISNULL(s.SoldQty, 0) AS SoldQty
FROM Purchased pu
JOIN dbo.Products p ON p.prd_pk = pu.ProductID
LEFT JOIN Sold s ON s.ProductID = pu.ProductID
WHERE ISNULL(s.SoldQty, 0) = 0   -- no sales
ORDER BY pu.PurchasedQty DESC; 
```


 16. ### Which products have expired on promotions but I still sell in other promotion price?
Rreturns multiple products with same name but different expiration date.

```sql
 SELECT DISTINCT 
    p.prd_description AS Product,
    exp.prm_effective AS ExpiredFrom,
    exp.prm_expires AS ExpiredTo,
    act.prm_effective AS ActiveFrom,
    act.prm_expires AS ActiveTo
FROM dbo.PromotionPrices exp
JOIN dbo.Products p ON p.prd_pk = exp.prm_prdfk
JOIN dbo.PromotionPrices act 
    ON act.prm_prdfk = exp.prm_prdfk
WHERE exp.prm_expires < GETDATE()       
  AND act.prm_effective <= GETDATE() 
  AND act.prm_expires >= GETDATE(); 
  ```


17. ### What is the selling price of coca cola 1.5 liter?
 Since coca cola is not listed in the product description so used YELLOW TAIL SHIRAZ instead.

```sql
 SELECT 
    p.prd_description AS Product,
    b.bar_barcode AS Barcode,
    prcc.prcc_price AS CurrentSellingPrice
FROM dbo.Products p
JOIN dbo.Barcodes b 
    ON b.bar_prdfk = p.prd_pk
JOIN dbo.Prices_Current prcc 
    ON prcc.prcc_barfk = b.bar_pk
WHERE p.prd_description LIKE '%YELLOW TAIL SHIRAZ%'; 
```
Change the product name here


18. ### What margin am I making on coca cola 1.5 liter?
 Since coca cola is not listed in the product description so used YELLOW TAIL SHIRAZ instead.

```sql
 SELECT 
    p.prd_description AS Product,
    b.bar_barcode AS Barcode,
    prcc.prcc_price AS SellingPrice,
    cstc.cstc_price AS CostPrice,
    (prcc.prcc_price - cstc.cstc_price) AS Margin,
    CAST(((prcc.prcc_price - cstc.cstc_price) * 100.0 / NULLIF(prcc.prcc_price, 0)) AS DECIMAL(10,2)) AS MarginPercent
FROM dbo.Products p
JOIN dbo.Barcodes b 
    ON b.bar_prdfk = p.prd_pk
JOIN dbo.Prices_Current prcc 
    ON prcc.prcc_barfk = b.bar_pk
JOIN dbo.SupplierProducts sp 
    ON sp.spr_prdfk = p.prd_pk
JOIN dbo.CostPrices_Current cstc 
    ON cstc.cstc_sprfk = sp.spr_pk
WHERE p.prd_description LIKE '%YELLOW TAIL SHIRAZ%'; 
```


19. ### Which products are over stock i.e what we sell weekly we have more in stock?

```sql
 WITH WeeklySales AS (
    SELECT 
        ps.psa_prdfk AS ProductID,
        SUM(ps.psa_quantity) / 6.0 AS AvgWeeklySales   -- 6 weeks avg
    FROM dbo.ProductSales ps
    WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE()) ---last year
    GROUP BY ps.psa_prdfk
)
SELECT 
    p.prd_description AS Product,
    bxp.bxp_instock AS CurrentStock,
    ws.AvgWeeklySales,
    (bxp.bxp_instock - ws.AvgWeeklySales) AS OverstockAmount
FROM dbo.BranchProducts bxp
JOIN dbo.Products p ON p.prd_pk = bxp.bxp_prdfk
JOIN WeeklySales ws ON ws.ProductID = p.prd_pk
WHERE bxp.bxp_instock > ws.AvgWeeklySales
ORDER BY OverstockAmount DESC; 
```


20. ### Which products are low in stock i.e the average sale for that product is less than instock figure?
 This returns the negative value of the some product stocks because in db we have negative stock values. 

```sql 
WITH AvgSales AS (
    SELECT 
        ps.psa_prdfk AS ProductID,
        AVG(ps.psa_quantity) AS AvgDailySales
    FROM dbo.ProductSales ps
    WHERE ps.psa_date >= DATEADD(YEAR, -1, GETDATE())   -- last 6 weeks
    GROUP BY ps.psa_prdfk
)
SELECT 
    p.prd_description AS Product,
    bxp.bxp_instock AS CurrentStock,
    a.AvgDailySales
FROM dbo.BranchProducts bxp
JOIN dbo.Products p ON p.prd_pk = bxp.bxp_prdfk
JOIN AvgSales a ON a.ProductID = p.prd_pk
WHERE a.AvgDailySales > ISNULL(bxp.bxp_instock, 0)
ORDER BY (a.AvgDailySales - bxp.bxp_instock) DESC; 
```


21. ### Which product is out of stock i.e stock level equals to zero?

```sql
 SELECT 
    p.prd_description AS Product,
    bxp.bxp_instock AS StockLevel,
    bxp.bxp_brnfk AS BranchID
FROM dbo.BranchProducts bxp
JOIN dbo.Products p 
    ON p.prd_pk = bxp.bxp_prdfk
WHERE ISNULL(bxp.bxp_instock, 0) = 0
  AND bxp.bxp_stocked = 1; 
  ```
This only consider stocked items.


22. ### How many products are in stock but the in stock figure is lower than the minimum stock level?

```sql
 SELECT 
    p.prd_description AS Product,
    bxp.bxp_instock AS CurrentStock,
    bxp.bxp_minstk AS MinStockLevel,
    bxp.bxp_brnfk AS BranchID
FROM dbo.BranchProducts bxp
JOIN dbo.Products p 
    ON p.prd_pk = bxp.bxp_prdfk
WHERE ISNULL(bxp.bxp_instock, 0) < ISNULL(bxp.bxp_minstk, 0);
 ```


23. ### How many coca cola 1.5 liter are in stock?
 Since coca cola is not listed in the product description so used WALLS MAGNUM CHILL instead.

```sql
 SELECT 
    p.prd_description AS Product,
    SUM(ISNULL(bxp.bxp_instock, 0)) AS TotalInStock
FROM dbo.Products p
JOIN dbo.BranchProducts bxp 
    ON bxp.bxp_prdfk = p.prd_pk
WHERE p.prd_description LIKE '%WALLS MAGNUM CHILL%'
GROUP BY p.prd_description;
 ```
