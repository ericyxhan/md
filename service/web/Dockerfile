# Build the single-page app, then serve the immutable bundle from nginx.
FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.29-alpine

# Shared contract value; compose passes it from service/contract.env.
ARG MD_WEB_PORT=80

# The SPA needs history fallback and long-lived hashed asset caching; the same
# config also adds the security headers Caddy would otherwise supply.
# The config is installed as a template so nginx's entrypoint substitutes the
# contract variables; NGINX_ENVSUBST_FILTER keeps it away from nginx's own
# runtime variables.
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE ${MD_WEB_PORT}

HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
