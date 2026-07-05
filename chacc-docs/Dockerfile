FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdocs build

FROM nginx:alpine AS production

COPY --from=builder /build/site /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]