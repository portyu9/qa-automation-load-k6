from pathlib import Path
import re

path = Path('README.md')
text = path.read_text(encoding='utf-8')
marker = '## Dependency maintenance\n'
section = '''## Confidence boundaries

Performance tooling can generate traffic capable of affecting real systems, so this framework treats **script correctness**, **traffic authorization**, **workload execution**, and **performance conclusions** as separate claims.

| Signal | Confidence gained | Deliberate limit |
| --- | --- | --- |
| Zero-traffic guardrail tests | Unsafe/missing target configuration and sustained-load authorization failures are rejected before scenario traffic can start | A guardrail proves refusal policy, not that an approved target has capacity for a requested experiment |
| `k6 inspect` profile contracts | Load/stress/soak scenarios, stages, thresholds, and configuration resolve successfully without executing sustained traffic | Inspection proves configuration shape, not latency, throughput, saturation, or service behavior |
| Deterministic loopback smoke | The packaged runtime can execute a bounded workload against the repository fixture, emit summary evidence, and satisfy basic thresholds | A local smoke proves workload health; it is not a capacity, scalability, endurance, or production service-level result |
| Explicit load/stress/soak run | The intended workload model executes against a target whose hostname is explicitly authorized for sustained traffic | Authorization is necessary but not sufficient: environment ownership, test window, data safety, downstream capacity, and incident controls remain operational prerequisites |
| Threshold result | The observed run satisfied or violated the configured threshold under that exact workload and environment | A threshold is not a timeless SLA claim; interpret it with scenario shape, concurrency/arrival model, data, duration, environment, and competing load |
| Runtime provenance gate | The executing k6 binary is tied to reviewed upstream source identity, a governed builder/runtime chain, and any explicit security override | Provenance identifies what executed; it does not by itself prove the binary is defect-free or appropriate for every environment |
| Built-image Trivy evidence | The produced runtime image is scanned as actually built, including OS packages and Go-binary dependencies | Scanner success is bounded by vulnerability intelligence, package detection, severity policy, and scan scope |
| Retained summary/profile evidence | CI proves the expected scenario or smoke actually resolved/executed and produced attributable machine-readable evidence | Evidence files do not replace native exit status, semantic validation, or experiment context |

A performance result is meaningful only when the **workload model, target authorization, environment, data, thresholds, and observation window** are all explicit. Never infer capacity from script-health smoke or from configuration inspection.

'''
if '## Confidence boundaries\n' not in text:
    if marker not in text:
        raise SystemExit('Dependency maintenance marker missing')
    text = text.replace(marker, section + marker)
path.write_text(text, encoding='utf-8')

patterns = [
    re.compile(r'\bk6\s+v?\d+(?:\.\d+)+', re.I),
    re.compile(r'\bGo\s+v?\d+(?:\.\d+)+', re.I),
    re.compile(r'\bAlpine\s+v?\d+(?:\.\d+)+', re.I),
    re.compile(r'\bTrivy\s+v?\d+(?:\.\d+)+', re.I),
    re.compile(r'\bDocker\s+v?\d+(?:\.\d+)+', re.I),
]
candidates = []
for md in [Path('README.md'), *Path('docs').rglob('*.md')]:
    for number, line in enumerate(md.read_text(encoding='utf-8').splitlines(), 1):
        if any(pattern.search(line) for pattern in patterns):
            candidates.append(f'{md}:{number}: {line}')
if candidates:
    raise SystemExit('Residual k6/tool version candidates:\n' + '\n'.join(candidates))
