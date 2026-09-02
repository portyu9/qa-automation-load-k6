ARG K6_VERSION=2.2.0
ARG K6_COMMIT=00a9a1b7f552d6bb4337278b10ae25aac0f4e666

# Release marker retained so Dependabot continues to surface upstream k6 image
# updates. The runtime binary is rebuilt below so security-qualified Go module
# overrides can be applied without losing exact upstream release provenance.
FROM grafana/k6:2.2.0@sha256:9bd01d6941fca969cb61bb57d2da5ee9b385fe2aa8881df3798c196564d6ace6 AS upstream-release

FROM --platform=$BUILDPLATFORM golang:1.27.0-alpine3.24@sha256:4c9fe60190a2a3350ddc51de80d0224b8a6698d12bdfc999fee45ea9d6c46dbc AS builder
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

# Emergency compiled-dependency security overrides live in a deliberately
# minimal repository-owned Go module. Each allowlisted version is applied to
# the ephemeral upstream checkout, verified after Go's module selection, and
# then vendored before compilation. The k6 release tag/commit remain unchanged.
COPY docker/security-overrides/go.mod /tmp/k6-security-overrides.mod
RUN awk ' \
      $1 == "require" && NF == 3 { print $2, $3; next } \
      $1 == "require" && $2 == "(" { in_require = 1; next } \
      in_require && $1 == ")" { in_require = 0; next } \
      in_require && NF == 2 { print $1, $2 } \
    ' /tmp/k6-security-overrides.mod > /tmp/k6-security-overrides.txt \
    && test "$(wc -l < /tmp/k6-security-overrides.txt)" -eq 2 \
    && while read -r MODULE VERSION; do \
         case "${MODULE}" in \
           golang.org/x/crypto|google.golang.org/grpc) GOFLAGS=-mod=mod go get "${MODULE}@${VERSION}" ;; \
           *) echo "unsupported security override: ${MODULE}" >&2; exit 1 ;; \
         esac; \
       done < /tmp/k6-security-overrides.txt \
    && while read -r MODULE VERSION; do \
         test "$(GOFLAGS=-mod=mod go list -m -f '{{.Version}}' "${MODULE}")" = "${VERSION}"; \
       done < /tmp/k6-security-overrides.txt \
    && go mod vendor \
    && CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
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