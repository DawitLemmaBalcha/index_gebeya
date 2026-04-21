FROM node:20-alpine

WORKDIR /app

# Only copy package.json initially (since lockfile doesn't exist yet)
COPY package.json .

# Install dependencies (this generates the lockfile inside the container)
RUN npm install --legacy-peer-deps

# Copy the rest of the code
COPY . .

# Expose port 5173 (Vite's default)
EXPOSE 5173

# Run dev server restricted to 0.0.0.0 so we can access it from outside
CMD ["npm", "run", "dev", "--", "--host"]
