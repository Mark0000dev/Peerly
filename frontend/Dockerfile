# Context: frontend/. Registry digests inspected 2026-11-09; update deliberately.
FROM node:24-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS build
ENV HUSKY=0 PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 NG_CLI_ANALYTICS=false
WORKDIR /workspace/frontend
RUN npm install --global npm@10.8.2 --ignore-scripts --no-audit --no-fund
COPY package.json package-lock.json .npmrc ./
COPY patches/ ./patches/
COPY tooling/font-watcher-patch.mjs tooling/font-watcher-hashes.json ./tooling/
# Keep the verified dependency patch lifecycle; only browser downloads/hooks are off.
RUN npm ci --no-audit --no-fund
COPY angular.json tsconfig.json tsconfig.app.json ./
COPY src/ ./src/
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 AS runtime
COPY deployment/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /workspace/frontend/dist/studymate/browser/ /usr/share/nginx/html/
USER 101:101
EXPOSE 8080
STOPSIGNAL SIGQUIT
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
ENTRYPOINT ["nginx", "-g", "daemon off;"]
