ARG K6_VERSION=2.2.0
ARG K6_COMMIT=00a9a1b7f552d6bb4337278b10ae25aac0f4e666

# Release marker retained so Dependabot continues to surface upstream k6 image
# updates. The runtime binary is rebuilt below because the current official
# 2.2.0 image was compiled with a Go toolchain that has fixed HIGH CVEs.
FROM grafana/k6:2.2.0@sha256:9bd01d6941fca969cb61bb57d2da5ee9b385fe2aa8881df3798c196564d6ace6 AS upstream-release

FROM --platform=$BUILDPLATFORM golang:1.26.7-alpine3.24@sha256:28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468 AS builder
ARG K6_VERSION
ARG K6_COMMIT
ARG TARGETOS
ARG TARGETARCH

WORKDIR /src/k6
RUN apk add --no-cache git=~2
RUN git init . \
    && git remote add origin https://github.com/grafana/k6.git \
    && git fetch --depth=1 origin "refs/tags/v${K6_VERSION}:refs/tags/v${K6_VERSION}" \
    && git checkout --detach "v${K6_VERSION}" \
    && test "$(git rev-parse HEAD)" = "${K6_COMMIT}"
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -trimpath -o /out/k6

FROM alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b AS runtime
ARG K6_VERSION
ARG K6_COMMIT

RUN apk upgrade --no-cache \
    && apk add --no-cache ca-certificates \
    && adduser -D -u 12345 -g 12345 k6

LABEL org.opencontainers.image.source="https://github.com/grafana/k6" \
      org.opencontainers.image.version="${K6_VERSION}" \
      org.opencontainers.image.revision="${K6_COMMIT}"

WORKDIR /src
COPY --from=builder /out/k6 /usr/bin/k6
COPY --chown=12345:12345 lib /src/lib
COPY --chown=12345:12345 tests /src/tests
RUN mkdir -p /src/reports && chown -R 12345:12345 /src

USER 12345
ENTRYPOINT ["k6"]

# Image startup is deliberately non-traffic-generating. A caller must select
# `run` explicitly and provide K6_BASE_URL before any scenario can send traffic.
CMD ["version"]
