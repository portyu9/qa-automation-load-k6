FROM grafana/k6:2.2.0

USER root
WORKDIR /src
COPY --chown=12345:12345 lib /src/lib
COPY --chown=12345:12345 tests /src/tests
RUN mkdir -p /src/reports && chown -R 12345:12345 /src

USER 12345

# Image startup is deliberately non-traffic-generating. A caller must select
# `run` explicitly and provide K6_BASE_URL before any scenario can send traffic.
CMD ["version"]
