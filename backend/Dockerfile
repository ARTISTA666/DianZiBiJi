FROM rust:1.88-slim-bookworm AS builder

WORKDIR /build

ARG BUILD_REVISION

RUN if [ -z "$BUILD_REVISION" ] || [ "$BUILD_REVISION" = "unversioned" ]; then \
        echo "BUILD_REVISION must be a full git revision" >&2; \
        exit 1; \
    fi

ENV CARGO_REGISTRIES_CRATES_IO_INDEX=sparse+https://rsproxy.cn/index/ \
    CARGO_HTTP_TIMEOUT=600 \
    CARGO_HTTP_LOW_SPEED_LIMIT=1 \
    CARGO_HTTP_MULTIPLEXING=false \
    CARGO_NET_RETRY=10

COPY Cargo.toml Cargo.lock ./
RUN mkdir -p src \
    && printf 'pub fn dependency_cache_marker() {}\n' > src/lib.rs \
    && printf 'fn main() {}\n' > src/main.rs \
    && cargo build --release --locked \
    && rm -rf src

COPY openapi.json ./openapi.json
COPY sql ./sql
COPY src ./src
ENV ELN_BUILD_REVISION=$BUILD_REVISION
RUN touch src/lib.rs src/main.rs \
    && cargo build --release --locked

FROM rust:1.88-slim-bookworm

ARG BUILD_REVISION

LABEL org.opencontainers.image.revision=$BUILD_REVISION

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-chi-sim \
        tesseract-ocr-eng \
        tesseract-ocr-ukr \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /storage /app/docs/experiments \
    && useradd --system --uid 10001 --user-group --home-dir /app eln \
    && chown -R eln:eln /storage /app

COPY --from=builder /build/target/release/eln-backend /usr/local/bin/eln-backend

WORKDIR /app
ENV MATURITY_ROOT=/app

USER eln

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/eln-backend"]
