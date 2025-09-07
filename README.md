# Load Testing Framework with k6

I built this repository to demonstrate a production‑ready load testing framework using k6. It allows me to define performance, stress and scalability tests for public APIs and run them locally or in CI/CD pipelines with Docker with GitHub Actions CI.

## Features

- **k6 test scripts** – Test scripts in the `tests/` directory cover smoke, load and stress scenarios against real APIs such as JSONPlaceholder. I define thresholds and checks to ensure service level objectives are met.
- **Docker integration** – A `Dockerfile` lets me run tests in a containerised environment for consistency across development machines and CI.
- **Scripts for local execution** – Shell scripts in `scripts/` streamline running tests with various parameters and output formats.
- **CI pipeline** – The GitHub Actions workflow under `.github/workflows/ci.yml` executes k6 tests automatically on pushes and pull requests, uploading results as artifacts.
- **Extensible structure** – I can add additional test scenarios, data files, or integrate results with Grafana/Loki for visualisation.

## Getting started

1. **Install k6** (optional)

   If you want to run k6 locally without Docker, install it from [k6.io](https://k6.io/docs/getting-started/installation/).

2. **Clone the repo**

   ```bash
   git clone https://github.com/portyu9/qa-automation-load-k6.git
   cd qa-automation-load-k6
   ```

3. **Run smoke test**

   Execute a quick smoke test against the JSONPlaceholder API to verify connectivity:

   ```bash
   k6 run tests/smoke.js
   ```

4. **Run load test with Docker**

   Use the provided Dockerfile to build an image and run a load test:

   ```bash
   docker build -t k6-load .
   docker run --rm -i k6-load run /src/tests/load.js
   ```

5. **CI execution**

   On each push, GitHub Actions will run the test suite defined in `ci.yml`. Check the Actions tab for results.

## Project structure

```
tests/
├── smoke.js      # Lightweight smoke test
└── load.js       # Load and stress test with thresholds

docker/
└── Dockerfile     # Container to run k6

scripts/
└── run_k6.sh      # Convenience script to run tests

.github/workflows/
└── ci.yml         # GitHub Actions workflow

README.md          # This file
```

I plan to iterate on these tests, add more scenarios, and integrate with Grafana dashboards for rich metrics.
