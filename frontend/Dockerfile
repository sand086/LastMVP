FROM node:20-alpine

WORKDIR /app

ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

COPY package.json ./
RUN yarn install

COPY . .

EXPOSE 3000

# Dev server (CRA hot reload). Para producción usa `yarn build` + un servidor estático.
CMD ["yarn", "start"]
