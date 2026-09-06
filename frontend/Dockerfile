# Local-dev image only: runs the Vite dev server directly. Production
# deploys the built static assets to S3 + CloudFront instead (blueprint
# section 17.1) -- there is no server process to containerize there.
FROM node:20-slim
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]
