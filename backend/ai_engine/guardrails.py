import time
from threading import Lock

class TrafficCop:
    def __init__(self, provider_name, min_interval_seconds):
        self.name = provider_name
        self.lock = Lock()
        self.last_call = 0
        self.interval = min_interval_seconds

    def enforce(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_call
            
            if elapsed < self.interval:
                sleep_time = self.interval - elapsed
                # Only log significant waits to keep logs clean
                if sleep_time > 0.5:
                    print(f"🚦 {self.name} Traffic Cop: Sleeping {sleep_time:.2f}s...")
                time.sleep(sleep_time)
            
            self.last_call = time.time()

# --- INSTANCES ---

# Groq: 14,400 RPD / 30 RPM. 
# 2.2s allows ~27 RPM, safe buffer.
groq_limiter = TrafficCop("Groq", min_interval_seconds=2.2)

# Gemini Free (2.5 Flash): 20 RPD / 5 RPM.
# 15.0s ensures we never burst above 4 RPM.
gemini_limiter = TrafficCop("Gemini", min_interval_seconds=15.0)