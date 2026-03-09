# Build stage
FROM node:25-alpine AS builder

WORKDIR /app

# Accept build arguments for Vite environment variables
# These are baked into the bundle at build time
ARG VITE_API_BASE_URL
ARG VITE_GOOGLE_CLIENT_ID

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build with environment variables from build args
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
RUN npm run build

# Runtime stage
FROM node:25-alpine

WORKDIR /app

# Install a simple HTTP server
RUN npm install -g serve

# Create a non-root user
RUN addgroup -g 1001 -S nodejs
RUN adduser -S assistantui -u 1001

# Copy built app from builder
COPY --from=builder /app/dist ./dist

# Set proper ownership
RUN chown -R assistantui:nodejs /app

# Switch to non-root user
USER assistantui

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]
