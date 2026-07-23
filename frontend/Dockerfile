FROM node:20-alpine

WORKDIR /app

# Install dependencies first (cached layer)
COPY package.json .
RUN npm install --legacy-peer-deps

# Copy source and build production bundle
COPY . .
RUN npm run build

# Serve the optimized production build
EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
