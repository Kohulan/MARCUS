# MARCUS v2 web UI, served by the stack's own nginx (backend-v2/docker-compose.yml, service
# nginx; build context: frontend-v2/). Stage 1 builds dist/ (client, Ketcher, SSR pre-render,
# check-dist); stage 2 is the edge image with the build and its locations file. nginx.conf
# itself stays a bind mount from backend-v2/docker/ and includes the locations file.

FROM node:22-alpine AS build
WORKDIR /src
COPY . .
RUN npm ci && npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=build /src/dist /usr/share/nginx/marcus-ui
COPY deploy/ui-locations.conf /etc/nginx/marcus/ui-locations.conf
