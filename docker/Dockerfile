FROM grafana/k6:2.2.0

WORKDIR /src
COPY lib /src/lib
COPY tests /src/tests
RUN mkdir -p /src/reports

# Smoke is intentionally the default. Load-generating profiles require an
# explicit K6_ALLOW_LOAD_TEST=true opt-in and an authorized target.
CMD ["run", "/src/tests/smoke.js"]
