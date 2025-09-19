import pyodbc
import re
from typing import List

# -----------------------------
# Configuration
# -----------------------------
DB_CONFIG = {
    "server": "DESKTOP-GMGNG7C",
    "database": "itsdrystock",
    "driver": "{ODBC Driver 17 for SQL Server}"  # Adjust if needed
}

TARGET_TABLES: List[str] = [
    "SupplierProducts", "PurchaseOrderlines", "Products", "PurchaseOrders",
    "Suppliers", "ProductSales", "TillTransactionHeaders", "TillTransactionDetails",
    "Barcodes", "PromotionPrices", "PromotionCosts", "Prices",
    "CostpricesHistory", "StockTransactions", "CostPrices_Current",
    "Prices_Current", "BranchProducts"
]

OUTPUT_FILE = "db_natural_language_report.txt"

_conn = None

def get_connection():
    global _conn
    if _conn is None:
        conn_str = (
            f"DRIVER={DB_CONFIG['driver']};"
            f"SERVER={DB_CONFIG['server']};"
            f"DATABASE={DB_CONFIG['database']};"
            "Trusted_Connection=yes;"
        )
        _conn = pyodbc.connect(conn_str)
    return _conn

# -----------------------------
# Helpers
# -----------------------------

def q_mark_list(items: List[str]) -> str:
    return ",".join([f"'{i}'" for i in items])

def safe_name(s: str) -> str:
    return re.sub(r"[^0-9A-Za-z_$.]", "", s)

def fetchall_dict(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]

# -----------------------------
# Queries
# -----------------------------
TABLES_IN = q_mark_list(TARGET_TABLES)

QUERIES = {
    "tables": f"""
        SELECT t.TABLE_SCHEMA, t.TABLE_NAME, t.TABLE_TYPE,
               CAST(ep.value AS NVARCHAR(500)) AS TABLE_DESCRIPTION
        FROM INFORMATION_SCHEMA.TABLES t
        LEFT JOIN sys.extended_properties ep
             ON ep.major_id = OBJECT_ID(t.TABLE_SCHEMA + '.' + t.TABLE_NAME)
            AND ep.minor_id = 0
            AND ep.name = 'MS_Description'
        WHERE t.TABLE_NAME IN ({TABLES_IN})
        ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME
    """,

    "columns": f"""
        SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE,
               c.IS_NULLABLE, c.COLUMN_DEFAULT,
               CAST(ep.value AS NVARCHAR(500)) AS COLUMN_DESCRIPTION
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN sys.extended_properties ep
             ON ep.major_id = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
            AND ep.minor_id = (
                SELECT sc.column_id
                FROM sys.columns sc
                WHERE sc.object_id = OBJECT_ID(c.TABLE_SCHEMA + '.' + c.TABLE_NAME)
                  AND sc.name = c.COLUMN_NAME
            )
            AND ep.name = 'MS_Description'
        WHERE c.TABLE_NAME IN ({TABLES_IN})
        ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
    """,

    "primary_keys": f"""
        SELECT t.name AS TableName, c.name AS ColumnName
        FROM sys.indexes i
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        JOIN sys.tables t ON i.object_id = t.object_id
        WHERE i.is_primary_key = 1
        AND t.name IN ({TABLES_IN})
    """,

    "foreign_keys": f"""
        SELECT fk.name AS FK_Name,
               tp.name AS ParentTable, ref.name AS ReferencedTable,
               cpa.name AS ParentColumn, cref.name AS ReferencedColumn
        FROM sys.foreign_keys fk
        INNER JOIN sys.tables tp ON fk.parent_object_id = tp.object_id
        INNER JOIN sys.tables ref ON fk.referenced_object_id = ref.object_id
        INNER JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        INNER JOIN sys.columns cpa ON fkc.parent_object_id = cpa.object_id AND fkc.parent_column_id = cpa.column_id
        INNER JOIN sys.columns cref ON fkc.referenced_object_id = cref.object_id AND fkc.referenced_column_id = cref.column_id
        WHERE tp.name IN ({TABLES_IN}) OR ref.name IN ({TABLES_IN})
    """,

    "constraints": f"""
        SELECT TABLE_NAME, CONSTRAINT_NAME, CONSTRAINT_TYPE
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
        WHERE TABLE_NAME IN ({TABLES_IN})
    """,

    "row_counts": f"""
        SELECT t.name AS TableName, SUM(p.rows) AS [RowCount]
        FROM sys.tables t
        INNER JOIN sys.partitions p ON t.object_id = p.object_id
        WHERE p.index_id IN (0,1)
        AND t.name IN ({TABLES_IN})
        GROUP BY t.name
    """
}

# -----------------------------
# Fetch metadata
# -----------------------------
def fetch_general_metadata():
    conn = get_connection()
    cur = conn.cursor()
    results = {}
    for k, q in QUERIES.items():
        cur.execute(q)
        results[k] = fetchall_dict(cur)
    return results

# -----------------------------
# Natural language concise report
# -----------------------------
def generate_natural_report(metadata: dict) -> str:
    row_counts = {r['TableName']: int(r['RowCount']) for r in metadata.get('row_counts', [])}

    pk_lookup = {}
    for pk in metadata.get('primary_keys', []):
        pk_lookup.setdefault(pk['TableName'], []).append(pk['ColumnName'])

    fk_list = metadata.get('foreign_keys', [])
    fk_by_table = {}
    for fk in fk_list:
        fk_by_table.setdefault(fk['ParentTable'], []).append(fk)

    columns = metadata.get('columns', [])
    cols_by_table = {}
    for c in columns:
        cols_by_table.setdefault(c['TABLE_NAME'], []).append(c)

    out_lines = ["Concise Database Schema Report\n"]

    for t in metadata.get('tables', []):
        schema = t.get('TABLE_SCHEMA')
        tname = t.get('TABLE_NAME')
        desc = t.get('TABLE_DESCRIPTION') or '(no description)'
        rows_count = row_counts.get(tname, 'unknown')
        cols = cols_by_table.get(tname, [])
        col_names = [c['COLUMN_NAME'] for c in cols]

        out_lines.append(f"Table: {schema}.{tname} ({rows_count} rows)")
        out_lines.append(f"Description: {desc}")
        out_lines.append(f"Columns ({len(cols)}): {', '.join(col_names)}")

        pk = pk_lookup.get(tname)
        if pk:
            out_lines.append(f"Primary key: {', '.join(pk)}")
        fks = fk_by_table.get(tname, [])
        if fks:
            fk_summaries = [f"{fk['ParentColumn']} -> {fk['ReferencedTable']}.{fk['ReferencedColumn']}" for fk in fks]
            out_lines.append(f"Foreign keys: {', '.join(fk_summaries)}")

        out_lines.append("")

    return "\n".join(out_lines)

# -----------------------------
# Main
# -----------------------------
if __name__ == '__main__':
    meta = fetch_general_metadata()
    report_text = generate_natural_report(meta)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(report_text)

    print(f"Concise report saved to: {OUTPUT_FILE}")

    if _conn is not None:
        _conn.close()
