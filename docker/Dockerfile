# k6 Dockerfile for load and smoke tests
# I build this image on top of the official k6 image, copy test scripts and set a default entrypoint.

FROM grafana/k6:0.50.0

# Set working directory
WORKDIR /src

# Copy tests into container
COPY tests /src/tests

# Default command runs the load test; override at runtime to run other scripts
CMD ["run", "/src/tests/load.js"]
