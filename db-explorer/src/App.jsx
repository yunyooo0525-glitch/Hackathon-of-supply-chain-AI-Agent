import React, { useState, useMemo } from 'react';
import { 
  BarChart3, 
  Package, 
  Building2, 
  Truck, 
  Search, 
  ChevronRight,
  Database,
  ArrowRight
} from 'lucide-react';
import dbData from './data.json';

const App = () => {
  const [activeTab, setActiveTab] = useState('Product');
  const [searchQuery, setSearchQuery] = useState('');

  const tabs = [
    { id: 'Company', label: 'Companies', icon: Building2 },
    { id: 'Product', label: 'Products', icon: Package },
    { id: 'Supplier', label: 'Suppliers', icon: Truck },
    { id: 'BOM', label: 'BOMs', icon: Database },
  ];

  const filteredData = useMemo(() => {
    let data = dbData[activeTab] || [];
    if (!searchQuery) return data;
    
    const query = searchQuery.toLowerCase();
    
    // Support "field:value" filtering
    if (query.includes(':')) {
      const [field, value] = query.split(':');
      const targetField = Object.keys(data[0] || {}).find(k => k.toLowerCase() === field);
      if (targetField) {
        // Use exact match for IDs, fuzzy for others
        if (targetField.toLowerCase().includes('id')) {
          return data.filter(item => String(item[targetField]).toLowerCase() === value.toLowerCase());
        }
        return data.filter(item => String(item[targetField]).toLowerCase().includes(value));
      }
    }

    return data.filter(item => {
      return Object.values(item).some(val => 
        String(val).toLowerCase().includes(query)
      );
    });
  }, [activeTab, searchQuery]);

  const stats = useMemo(() => {
    return {
      Companies: dbData.Company?.length || 0,
      Products: dbData.Product?.length || 0,
      Suppliers: dbData.Supplier?.length || 0,
    };
  }, []);

  const renderCard = (item) => {
    switch (activeTab) {
      case 'Company':
        const companyProducts = dbData.Product.filter(p => p.CompanyId === item.Id);
        return (
          <div key={item.Id} className="card" onClick={() => {
            setActiveTab('Product');
            setSearchQuery(`companyid:${item.Id}`);
          }}>
            <div className="card-title">{item.Name}</div>
            <div className="card-subtitle">ID: {item.Id}</div>
            <div className="tag tag-finished" style={{ marginTop: '0.5rem' }}>
              {companyProducts.length} Products
            </div>
          </div>
        );
      case 'Product':
        return (
          <div key={item.Id} className="card">
            <div className="card-title">{item.SKU}</div>
            <div className="card-subtitle">
              Company ID: {item.CompanyId}
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <span className={`tag ${item.Type === 'finished-good' ? 'tag-finished' : 'tag-raw'}`}>
                {item.Type.replace('-', ' ')}
              </span>
              {item.Type === 'finished-good' && (
                <span className="tag" style={{ background: 'rgba(139, 92, 246, 0.1)', color: 'var(--accent-primary)' }}>
                  Has BOM
                </span>
              )}
            </div>
          </div>
        );
      case 'Supplier':
        const supplierProducts = dbData.Supplier_Product.filter(sp => sp.SupplierId === item.Id);
        return (
          <div key={item.Id} className="card">
            <div className="card-title">{item.Name}</div>
            <div className="card-subtitle">ID: {item.Id}</div>
            <div className="tag tag-raw" style={{ marginTop: '0.5rem' }}>
              Supplies {supplierProducts.length} SKU(s)
            </div>
          </div>
        );
      case 'BOM':
        const prod = dbData.Product.find(p => p.Id === item.ProducedProductId);
        const components = dbData.BOM_Component.filter(bc => bc.BOMId === item.Id);
        return (
          <div key={item.Id} className="card">
            <div className="card-title">BOM {item.Id}</div>
            <div className="card-subtitle">
              Produces: <strong>{prod?.SKU || `Product ${item.ProducedProductId}`}</strong>
            </div>
            <div className="bom-components">
              <div className="component-item">
                <ChevronRight size={14} style={{ verticalAlign: 'middle' }} />
                Contains {components.length} components
              </div>
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="logo">DB EXPLORER</div>
        <nav>
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <div 
                key={tab.id}
                className={`nav-item ${activeTab === tab.id ? 'active' : ''}`}
                onClick={() => {
                  setActiveTab(tab.id);
                  setSearchQuery('');
                }}
              >
                <Icon size={20} />
                <span>{tab.label}</span>
              </div>
            );
          })}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="header">
          <div className="search-container">
            <Search size={18} className="text-muted" />
            <input 
              type="text" 
              className="search-input" 
              placeholder={`Search ${activeTab.toLowerCase()}s...`}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <div className="user-profile">
            <span className="text-muted text-sm">v1.0.0</span>
          </div>
        </header>

        <div className="view-area">
          {/* Stats Bar */}
          <div className="stats-container">
            <div className="stat-item">
              <div className="stat-value">{stats.Companies}</div>
              <div className="stat-label">Companies</div>
            </div>
            <div className="stat-item">
              <div className="stat-value">{stats.Products}</div>
              <div className="stat-label">Products</div>
            </div>
            <div className="stat-item">
              <div className="stat-value">{stats.Suppliers}</div>
              <div className="stat-label">Suppliers</div>
            </div>
          </div>

          <h2 style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {tabs.find(t => t.id === activeTab)?.label}
            <span className="text-muted" style={{ fontSize: '1rem', fontWeight: 400 }}>
              ({filteredData.length} records)
            </span>
          </h2>

          <div className="data-grid">
            {filteredData.slice(0, 100).map(item => renderCard(item))}
          </div>
          
          {filteredData.length > 100 && (
            <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
              Showing first 100 results. Use search to find specific items.
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default App;
