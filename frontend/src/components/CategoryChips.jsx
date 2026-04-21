import { Smartphone, Laptop, Car, Home, Shirt, Grid, Sparkles, SprayCan, Heart, Armchair } from 'lucide-react';

// Define the Strict Taxonomy for the Frontend
const TAXONOMY = {
  'Electronics': {
    icon: Smartphone,
    subs: ['Mobile Phones', 'Laptops', 'Tablets', 'Audio', 'Accessories', 'Cameras', 'Gaming']
  },
  'Fashion': {
    icon: Shirt,
    subs: ['Men', 'Women', 'Shoes', 'Jewelry', 'Accessories', 'Bags']
  },
  'Beauty': {
    icon: Sparkles,
    subs: ['Makeup', 'Fragrance', 'Nail Care']
  },
  'Personal Care': {
    icon: SprayCan, // Or Heart/Droplet
    subs: ['Skincare', 'Hair Care', 'Treatments', 'Hygiene']
  },
  'Vehicles': {
    icon: Car,
    subs: ['Cars', 'Motorcycles', 'Parts & Accessories']
  },
  'Real Estate': {
    icon: Home,
    subs: ['Houses', 'Apartments', 'Land', 'Commercial']
  },
  'Home': {
    icon: Armchair,
    subs: ['Furniture', 'Appliances', 'Decor', 'Kitchenware']
  }
};

export default function CategoryChips({ activeCategory, setActiveCategory, activeSubcategory, setActiveSubcategory }) {
  
  const handleMainClick = (catId) => {
    if (activeCategory === catId) {
      // Toggle off
      setActiveCategory('all');
      setActiveSubcategory('all');
    } else {
      // Select new
      setActiveCategory(catId);
      setActiveSubcategory('all'); // Reset sub when switching main
    }
  };

  const currentSubs = TAXONOMY[activeCategory]?.subs || [];

  return (
    <div className="flex flex-col gap-2 pb-2">
      
      {/* --- Row 1: Main Categories --- */}
      <div className="w-full overflow-x-auto no-scrollbar">
        <div className="flex gap-2 px-4 min-w-max">
          <button
            onClick={() => handleMainClick('all')}
            className={`
              flex items-center space-x-2 px-4 py-2.5 rounded-full text-xs font-semibold transition-all duration-300
              ${activeCategory === 'all' 
                ? 'bg-gray-900 text-white shadow-lg shadow-gray-200 scale-105' 
                : 'bg-white text-gray-500 border border-gray-100'}
            `}
          >
            <Grid size={14} />
            <span>All</span>
          </button>

          {Object.entries(TAXONOMY).map(([key, data]) => {
            const Icon = data.icon;
            const isActive = activeCategory === key;
            return (
              <button
                key={key}
                onClick={() => handleMainClick(key)}
                className={`
                  flex items-center space-x-2 px-4 py-2.5 rounded-full text-xs font-semibold transition-all duration-300
                  ${isActive 
                    ? 'bg-blue-600 text-white shadow-md shadow-blue-200 scale-105 ring-2 ring-blue-100' 
                    : 'bg-white text-gray-500 border border-gray-100 hover:border-blue-100'}
                `}
              >
                <Icon size={14} className={isActive ? 'text-white' : 'text-gray-400'} />
                <span>{key}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* --- Row 2: Subcategories (Conditional) --- */}
      {currentSubs.length > 0 && (
        <div className="w-full overflow-x-auto no-scrollbar animate-fade-in-up">
          <div className="flex gap-2 px-4 min-w-max">
            <button
               onClick={() => setActiveSubcategory('all')}
               className={`px-3 py-1.5 rounded-full text-[11px] font-medium border transition-colors
                 ${activeSubcategory === 'all' 
                   ? 'bg-gray-100 border-gray-300 text-gray-900' 
                   : 'bg-transparent border-transparent text-gray-400 hover:text-gray-600'}
               `}
            >
              All {activeCategory}
            </button>
            
            {currentSubs.map((sub) => (
              <button
                key={sub}
                onClick={() => setActiveSubcategory(sub)}
                className={`
                  px-3 py-1.5 rounded-full text-[11px] font-medium border transition-colors
                  ${activeSubcategory === sub
                    ? 'bg-blue-50 border-blue-200 text-blue-700'
                    : 'bg-white border-gray-100 text-gray-500 hover:border-gray-200'}
                `}
              >
                {sub}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}