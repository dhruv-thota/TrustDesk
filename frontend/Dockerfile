# Stage 1: Build production bundle
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: Serve with lightweight Nginx
FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

HEALTHCHECK --interval=5s --timeout=3s --retries=3 \
  CMD wget -q -O - http://127.0.0.1:5173/ || exit 1

CMD ["nginx", "-g", "daemon off;"]

