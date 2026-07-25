import { Compass, Bell, Store } from 'lucide-react';

export default function BottomNav({ activeTab, setActiveTab }) {
  const navItems = [
    { id: 'explore', icon: Compass, label: 'Explore' },
    { id: 'alerts', icon: Bell, label: 'Alerts' },
    { id: 'stores', icon: Store, label: 'Stores' },
  ];

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-200 pb-safe">
      <div className="flex justify-between items-center w-full max-w-lg mx-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className="group relative flex flex-col items-center justify-center flex-1 py-2"
            >
              {/* Active indicator bar at top */}
              {isActive && (
                <div className="absolute top-0 left-1/4 right-1/4 h-0.5 rounded-full bg-brand-500" />
              )}

              <div
                className={`p-1.5 rounded-xl transition-all duration-300 ${
                  isActive
                    ? 'bg-brand-50 text-brand-600'
                    : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Icon size={24} strokeWidth={isActive ? 2.5 : 2} />
              </div>

              <span
                className={`text-[10px] font-semibold transition-colors duration-200 ${
                  isActive ? 'text-brand-600' : 'text-gray-400'
                }`}
              >
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
