FROM node:24-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_BASE_URL=/api
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN npm run build
RUN npm prune --omit=dev && npm cache clean --force

ENV NODE_ENV=production

RUN chown -R node:node /app
USER node

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]
