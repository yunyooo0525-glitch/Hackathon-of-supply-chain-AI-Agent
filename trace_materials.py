import sqlite3
import argparse

def find_materials_and_suppliers(db_path, company_name, product_sku):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if the company and product exist
    cursor.execute("""
        SELECT p.Id 
        FROM Company c 
        JOIN Product p ON c.Id = p.CompanyId 
        WHERE c.Name = ? AND p.SKU = ?
    """, (company_name, product_sku))
    
    product_exists = cursor.fetchone()
    if not product_exists:
        print(f"❌ 找不到公司 '{company_name}' 下的 '{product_sku}' 产品，请检查输入是否有误。")
        conn.close()
        return

    # Execute the query to find components and their suppliers
    query = """
        SELECT
            rm.SKU as MaterialSKU,
            GROUP_CONCAT(COALESCE(s.Name, '暂无供应商数据'), ' | ') as Suppliers
        FROM Company c
        JOIN Product p ON c.Id = p.CompanyId
        JOIN BOM b ON p.Id = b.ProducedProductId
        JOIN BOM_Component bc ON b.Id = bc.BOMId
        JOIN Product rm ON bc.ConsumedProductId = rm.Id
        LEFT JOIN Supplier_Product sp ON rm.Id = sp.ProductId
        LEFT JOIN Supplier s ON sp.SupplierId = s.Id
        WHERE c.Name = ? AND p.SKU = ?
        GROUP BY rm.SKU
    """
    
    cursor.execute(query, (company_name, product_sku))
    results = cursor.fetchall()
    
    print(f"\n🔍 查询结果: [公司] {company_name} | [产品] {product_sku}")
    print("=" * 60)
    
    if not results:
        print("未找到该产品的 BOM（物料清单）或原材料数据。")
    else:
        for idx, row in enumerate(results, start=1):
            material_sku = row[0]
            suppliers = row[1]
            print(f"{idx}. 原材料 SKU: {material_sku}")
            print(f"   供应商: {suppliers}")
            print("-" * 60)

    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询某公司旗下特定产品的对应原材料及供应商。")
    parser.add_argument("-c", "--company", required=True, help="品牌公司名称 (例如: '21st Century')")
    parser.add_argument("-p", "--product", required=True, help="产品 SKU (例如: 'FG-iherb-10421')")
    parser.add_argument("-d", "--db", default="db.sqlite", help="SQLite 数据库文件路径 (默认: db.sqlite)")
    
    args = parser.parse_args()
    find_materials_and_suppliers(args.db, args.company, args.product)
