import { Home, Search, Heart, User } from 'lucide-react';

export default function BottomNav({ activeTab, setActiveTab }) {
  const navItems = [
    { id: 'home', icon: Home, label: 'Home' },
    { id: 'search', icon: Search, label: 'Visual' }, // Changed label for future Visual Search
    { id: 'saved', icon: Heart, label: 'Saved' },
    { id: 'profile', icon: User, label: 'Profile' },
  ];

  return (
    <div className="bg-white/80 backdrop-blur-xl border border-gray-200/50 sm:rounded-full sm:mb-6 shadow-[0_8px_30px_rgb(0,0,0,0.04)] px-6 py-3">
      <div className="flex justify-between items-center w-full">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className="group flex flex-col items-center justify-center w-16 relative"
            >
              <div className={`
                p-2 rounded-xl transition-all duration-300 mb-1
                ${isActive ? 'bg-blue-50 text-blue-600 translate-y-[-2px]' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'}
              `}>
                <Icon size={24} strokeWidth={isActive ? 2.5 : 2} />
              </div>
              
              <span className={`text-[10px] font-semibold transition-colors duration-200 ${isActive ? 'text-blue-600' : 'text-gray-400'}`}>
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}