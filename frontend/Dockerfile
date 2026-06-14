ARG NODE_BASE_IMAGE=node:24-alpine
FROM ${NODE_BASE_IMAGE}

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
ARG NPM_REGISTRY=https://registry.npmjs.org/
RUN corepack enable && corepack prepare pnpm@11.5.1 --activate \
  && pnpm config set registry "$NPM_REGISTRY" \
  && pnpm install --frozen-lockfile

COPY index.html vite.config.ts tsconfig.json ./
COPY src ./src

ARG VITE_API_BASE_URL=http://localhost:8000/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN pnpm build

EXPOSE 5173

CMD ["pnpm", "start"]
