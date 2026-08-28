FROM grafana/k6:2.2.0

USER root
WORKDIR /src
COPY --chown=12345:12345 lib /src/lib
COPY --chown=12345:12345 tests /src/tests
RUN mkdir -p /src/reports && chown -R 12345:12345 /src

USER 12345

# Smoke is intentionally the default. Load-generating profiles require an
# explicit K6_ALLOW_LOAD_TEST=true opt-in and an authorized target.
CMD ["run", "/src/tests/smoke.js"]
