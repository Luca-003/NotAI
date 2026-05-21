# syntax=docker/dockerfile:1.7
# NotAI - web React + Vite. Multi-stage: dev (Vite HMR) + builder (npm build) + runtime (Nginx).

ARG NODE_VERSION=20

# -----------------------------------------------------------------------------
# Stage dev: Vite dev server con HMR
# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS dev
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install
COPY apps/web/ ./
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# -----------------------------------------------------------------------------
# Stage builder: produce static bundle
# -----------------------------------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS builder
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY apps/web/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage runtime: Nginx servendo build statica
# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
  CMD wget -qO- http://localhost:80/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
