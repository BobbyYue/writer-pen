#!/usr/bin/env python3
"""Sequence the native literary workflow; never generate prose or review verdicts."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def need(value, message):
    if not value:
        raise ValueError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path.read_bytes())}


def verify_ref(item):
    path = Path(item['path'])
    need(not path.is_symlink() and reference(path) == item, 'Input snapshot changed: ' + str(path))


def frozen(path, data):
    """An interrupted start may reuse identical bytes, never replace different ones."""
    path = Path(path)
    need(not path.is_symlink(), 'Snapshot must not be a symbolic link')
    if path.exists():
        need(path.read_bytes() == data, 'Existing snapshot differs; preserve the incomplete task: ' + str(path))
    else:
        with path.open('xb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    path.chmod(0o400)
    return reference(path)


def frozen_json(path, value):
    return frozen(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


@contextmanager
def locked(task):
    need(task.is_dir() and not task.is_symlink(), 'Task directory is missing or unsafe')
    fd = os.open(task / '.writer-lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def paths_for(task):
    return {name: str(task / suffix) for name, suffix in {
        'task': '', 'native': 'native', 'lifecycle': 'lifecycle', 'inputs': 'inputs',
        'records': 'records', 'characters': 'characters',
        'request': 'inputs/request.json', 'contract': 'inputs/contract.json',
        'plan': 'inputs/plan.json'}.items()}


def read_workflow(task):
    path = task / 'workflow.json'
    need(path.is_file() and not path.is_symlink(),
         'workflow.json is missing; this may be an incomplete start or a legacy run. Do not reset its records.')
    flow = load(path)
    need(flow.get('format_version') == 1 and flow.get('paths') == paths_for(task),
         'Workflow path map does not belong to this task directory')
    return flow


def verify_inputs(flow):
    for item in flow['inputs']:
        verify_ref(item)


def request_data(path):
    request = load(path)
    need(isinstance(request, dict), 'Request must be a JSON object')
    need(not set(request) - {'contract', 'plan', 'source', 'sources'}, 'Unknown request fields')
    need(isinstance(request.get('contract'), dict) and isinstance(request.get('plan'), dict),
         'Request needs contract and plan objects')
    need(not ('source' in request and 'sources' in request), 'Use source or sources, not both')
    sources = request.get('sources', [request['source']] if request.get('source') else [])
    need(isinstance(sources, list) and all(isinstance(p, str) and p.strip() for p in sources),
         'sources must be an ordered list of paths; its first file is the native designated source')
    base = Path(path).resolve().parent
    sources = [(base / p).resolve() for p in sources]
    import writing_run as native
    import writing_lifecycle as lifecycle
    contract, plan = request['contract'], request['plan']
    source = native.artifact('source', native.read_text(sources[0])) if sources else None
    native.validate_contract(contract, source)
    lifecycle.validate_plan(plan, 'literary', [reference(p) for p in sources])
    need(plan.get('purpose', '').strip() == contract['goal'].strip(), 'Plan purpose must match contract goal')
    need(plan.get('scope', '').strip() == contract['scope'].strip(), 'Plan scope must match contract scope')
    need(all(isinstance(p, str) and p.strip() for p in plan['constraints']), 'Plan constraints must be nonempty text')
    need({p.strip() for p in plan['constraints']} == {p.strip() for p in contract.get('constraints', [])},
         'Plan constraints must match the native contract')
    need(plan['material']['mode'] != 'fiction' or contract['fiction'] == 'allowed',
         'Plan fiction requires native fiction permission')
    return request, sources


def create_workflow(args, task):
    import runtime_bundle
    request, sources = request_data(args.request)
    task.mkdir(mode=0o700, parents=True, exist_ok=True)
    with locked(task):
        if (task / 'workflow.json').exists():
            return read_workflow(task)
        need(not any((task / name).exists() for name in ('native', 'lifecycle', '_runtime')),
             'Incomplete start without a path map; preserve the task and registry for explicit recovery. No records were reset.')
        paths = paths_for(task)
        for key in ('inputs', 'records', 'characters'):
            path = Path(paths[key])
            need(not path.is_symlink(), 'Unsafe task subdirectory: ' + key)
            path.mkdir(mode=0o700, exist_ok=True)
        inputs = [frozen(paths['request'], Path(args.request).read_bytes())]
        snapshots = []
        for index, source in enumerate(sources):
            data = source.read_bytes()
            need(data.decode('utf-8').strip(), 'Source is empty')
            snapshot = frozen(Path(paths['inputs']) / ('source-' + str(index + 1) + source.suffix), data)
            snapshots.append({'original_path': str(source), 'snapshot': snapshot})
            inputs.append(snapshot)
        # Capture plan dependencies as well, keeping the original request unmodified.
        plan = json.loads(json.dumps(request['plan']))
        base = Path(args.request).resolve().parent
        dependencies = [(plan.get('wordlists', {}), key) for key in plan.get('wordlists', {})]
        dependencies += [(item, 'source_path') for item in plan.get('evidence_items', []) if item.get('source_path')]
        for index, (owner, key) in enumerate(dependencies):
            source = (base / owner[key]).resolve()
            item = frozen(Path(paths['inputs']) / ('dependency-' + str(index + 1) + source.suffix), source.read_bytes())
            owner[key] = item['path']
            inputs.append(item)
        inputs.append(frozen_json(paths['contract'], request['contract']))
        inputs.append(frozen_json(paths['plan'], plan))
        pin = runtime_bundle.pin(task, skill_root=ROOT)
        runtime_bundle.verify(pin)
        flow = {'format_version': 1, 'task_id': args.task_id,
                'registry': str(Path(args.registry).absolute()) if args.registry else None,
                'paths': paths, 'inputs': inputs, 'sources': snapshots, 'runtime': pin}
        frozen_json(task / 'workflow.json', flow)
        return flow


def initialize(flow, args):
    import writing_run as native
    import writing_lifecycle as lifecycle
    import writing_execution as execution
    need(args.task_id == flow['task_id'], 'Task ID differs from the authoritative path map')
    if args.registry:
        need(str(Path(args.registry).absolute()) == flow['registry'], 'Registry differs from the original start')
    need(Path(args.request).read_bytes() == Path(flow['paths']['request']).read_bytes(),
         'Request changed; resume the original task, not a replacement contract')
    verify_inputs(flow)
    paths = flow['paths']
    life, run = Path(paths['lifecycle']), Path(paths['native'])
    if not (life / 'lifecycle.json').exists():
        need(not life.exists(), 'Incomplete lifecycle directory; preserve it for explicit recovery')
        lifecycle.init_run(life, paths['plan'], 'literary', [s['snapshot']['path'] for s in flow['sources']])
    if not (run / 'run.json').exists():
        need(not run.exists(), 'Incomplete native directory; preserve it for explicit recovery')
        native.init_run(run, load(paths['contract']), flow['sources'][0]['snapshot']['path'] if flow['sources'] else None)
    with native.session(run) as state:
        need(state['contract'] == load(paths['contract']), 'Native contract differs from the request snapshot')
        native.lifecycle_registration(state, str(life))
    execution.initialize(life, flow['task_id'], flow['registry'])
    ready(flow)
    return {'status': 'initialized', 'workflow': str(Path(paths['task']) / 'workflow.json'),
            'next': 'prepare', 'boundary': 'Records initialized before units; not a literary-quality or generation-order claim.'}


def ready(flow):
    import writing_run as native
    import writing_lifecycle as lifecycle
    import writing_execution as execution
    verify_inputs(flow)
    paths = flow['paths']
    with lifecycle.session(paths['lifecycle']) as state:
        need(state['profile'] == 'literary' and state['plan'] == load(paths['plan']), 'Lifecycle plan differs from the snapshot')
        link = state.get('execution')
        need(link and link['task_id'] == flow['task_id'], 'Initialization is incomplete; resume start with the same task ID')
        if flow['registry']:
            need(link['registry'] == flow['registry'], 'Execution registry changed')
    with execution.task(paths['lifecycle']):
        pass
    with native.session(paths['native']) as state:
        need(state['contract'] == load(paths['contract']), 'Native contract differs from the snapshot')
        expected = flow['sources'][0]['snapshot']['path'] if flow['sources'] else None
        need((state['source']['origin'] if state['source'] else None) == expected, 'Native designated source differs')
        native.lifecycle_registration(state, paths['lifecycle'])


def prepare(flow, args):
    import character_record
    import writing_run as native
    record = args.record
    if args.character:
        directory = Path(flow['paths']['characters'])
        record = directory / (args.id + '.record.json')
        if record.exists():
            sealed = character_record.verify(record)
            need(Path(sealed['snapshot']).read_bytes() == Path(args.character).read_bytes(),
                 'Character baseline differs; choose a new record ID, never overwrite')
        else:
            record = character_record.seal(args.character, directory, args.id)['manifest']
    with native.session(flow['paths']['native'], True) as state:
        return native.prepare(state, record, args.reason, args.timing, lifecycle_run=flow['paths']['lifecycle'])


def draft(flow, args):
    import writing_run as native
    import writing_lifecycle as lifecycle
    paths = flow['paths']
    with native.session(paths['native']) as state:
        need(state['preparations'], 'Prepare and seal the required character record before draft checkpoints')
        need('draft:' + args.id not in native.objects(state), 'Draft ID already exists; use a new version')
    with lifecycle.session(paths['lifecycle']) as state:
        route = state['plan']['reading_path']
    if args.units:
        units = load(args.units)
        need(isinstance(units, list) and units, 'Units input must be a nonempty list of {text, record} paths')
        base = Path(args.units).resolve().parent
        units = [(base / u['text'], base / u['record']) for u in units]
    else:
        need(len(route) == 1 and args.record, 'Supply --units for a multi-unit plan; a single-unit plan needs --record')
        units = [(Path(args.file), Path(args.record))]
    ids = [load(record)['unit_id'] for _, record in units]
    need(len(ids) == len(set(ids)) and set(ids) == {u['id'] for u in route},
         'Draft checkpoints must cover exactly the planned units')
    for text, record in units:
        lifecycle.record_unit(paths['lifecycle'], text, record)
    with native.session(paths['native'], True) as state:
        return native.add_draft(state, args.id, args.file, lifecycle_run=paths['lifecycle'], checkpoint=ids[-1])


def self_review(flow, args):
    import writing_run as native
    need(args.clean or args.comparison, 'Supply --clean and/or --comparison input paths')
    with native.session(flow['paths']['native'], True) as state:
        result = []
        for phase in ('clean', 'comparison'):
            path = getattr(args, phase)
            if path:
                body = load(path)
                need(body.get('phase') == phase, 'Self-review input has the wrong phase')
                result.append(native.add_review(state, body))
    return {'status': 'self-review-recorded', 'records': result, 'next': 'decide'}


def bridge(flow):
    import writing_execution as execution
    import writing_lifecycle as lifecycle
    paths = flow['paths']
    packets = execution.packet_map(paths['lifecycle'])
    with lifecycle.session(paths['lifecycle']) as state:
        number = state['rounds'][-1]['round']
    path = Path(paths['records']) / ('review-' + str(number) + '.packets.json')
    frozen_json(path, packets)
    return {'status': 'review-required', 'round': number, 'packets': str(path),
            'host_bridge': {'script': str(ROOT / 'scripts/writing_host.js'), 'function': 'runWritingHost',
                            'options': {'skillRoot': str(ROOT), 'run': paths['lifecycle'],
                                        'packets': str(path), 'nativeRun': paths['native']}},
            'next': 'Invoke the bridge with actual host tools, then finish-review. Missing capabilities block; never synthesize returns.'}


def candidate(flow, args):
    import writing_run as native
    import writing_lifecycle as lifecycle
    paths = flow['paths']
    with native.session(paths['native']) as state:
        item = native.current(state)
        need(reference(item['origin'])['sha256'] == item['sha256'], 'Working draft changed; register a new version')
        reviews = native.latest_reviews(state)
        need({'clean', 'comparison'} <= set(reviews), 'Complete native clean/comparison self-review first')
        decisions = [d for d in state['decisions'] if d['draft_id'] == item['id']]
        need(decisions and decisions[-1]['review_ids'] == {p: r['id'] for p, r in reviews.items()},
             'Record a current native decision before candidate')
    artifact = reference(item['origin'])
    with lifecycle.session(paths['lifecycle']) as state:
        previous = state['candidates'][-1] if state['candidates'] else None
        batch = state['rounds'][-1] if state['rounds'] else None
    if previous and previous['artifact'] == artifact:
        if args.report:
            need(reference(args.report) == previous['report'], 'Report differs from the registered candidate')
        if args.assessment:
            need(reference(args.assessment) == previous['record'], 'Assessment differs from the registered candidate')
        if args.geometry:
            need(load(previous['report']['path']).get('geometry') == reference(args.geometry),
                 'Geometry differs from the registered candidate')
        if batch and batch['artifact_sha256'] == artifact['sha256']:
            if batch['verdict'] is None:
                return bridge(flow)
            return {'status': 'review-already-recorded', 'next': 'status; do not open another round for a command retry'}
    else:
        report = Path(args.report) if args.report else Path(paths['records']) / (item['id'].replace(':', '-') + '.measure.json')
        if not report.exists():
            lifecycle.measure(paths['lifecycle'], item['origin'], report, args.geometry)
        if args.geometry:
            need(load(report).get('geometry') == reference(args.geometry), 'Existing report uses different geometry; choose a new report path')
        if not args.assessment:
            return {'status': 'assessment-required', 'report': str(report.resolve()),
                    'assessment_template': str(report.resolve()) + '.assessment.json',
                    'next': 'Write contextual observations and signal decisions, then repeat candidate --assessment PATH. No review started.'}
        lifecycle.register_candidate(paths['lifecycle'], item['origin'], item['origin'], report, args.assessment)
    lifecycle.start_review(paths['lifecycle'], item['origin'], args.stage)
    return bridge(flow)


def finish_review(flow, args):
    import writing_run as native
    import writing_lifecycle as lifecycle
    import writing_execution as execution
    paths = flow['paths']
    with lifecycle.session(paths['lifecycle']) as state:
        need(state['rounds'], 'Start a candidate review first')
        batch = state['rounds'][-1]
    with execution.task(paths['lifecycle']) as task:
        managed = task['batches'][str(batch['round'])]
        jobs = managed['jobs']
        need(set(jobs) == set(execution.policy()['roles']) and all(j['status'] == 'captured' for j in jobs.values()),
             'Actual reviewer captures are incomplete; resume the same host bridge, not a new round')
        results = {role: job['result']['path'] for role, job in jobs.items()}
        for job in jobs.values():
            need(reference(job['result']['path']) == job['result'], 'Captured reviewer result changed')
    if args.results:
        need(load(args.results) == results, 'Results must be the exact captured role-path map')
    # Commit actual role returns before asking the author to make editorial choices.
    with native.session(paths['native'], True) as state:
        old = native.final_reviewers(state)
        for role, path in results.items():
            body = load(path)
            need(body.get('role') == role, 'Captured return has the wrong role')
            existing = old.get(role)
            if existing and existing['result_path'] == path and existing['result_sha256'] == reference(path)['sha256']:
                need(existing['body'] == body, 'Stored native reviewer differs from capture')
            else:
                native.add_reviewer_record(state, body, path)
        payload = native.native_review_payload(state)
    pending = payload.get('pending_editorial', [])
    decisions = payload.get('editorial_decisions', [])
    missing = [f for f in pending if not any(all(d.get(k) == f.get(k) for k in
               ('role', 'finding_id', 'reviewer_receipt')) for d in decisions)]
    if missing:
        return {'status': 'pending-editorial', 'pending_editorial': missing, 'round': batch['round'],
                'next': 'author-choice --file PATH, then resume finish-review; the same review batch remains open'}
    output = Path(paths['lifecycle']) / ('review-' + str(batch['round'])) / 'native-result.json'
    with native.session(paths['native'], True) as state:
        if output.exists():
            native.bind_review_result(state, output)
        else:
            native.write_review_result(state, output)
    if batch['verdict'] is None:
        lifecycle.finish_review(paths['lifecycle'], output, payload['status'])
    else:
        need(batch['result'] == reference(output) and batch['verdict'] == payload['status'],
             'Completed review differs; no old aggregate was replaced')
    execution.verify_reviews(paths['lifecycle'], [str(output)])
    return {'status': 'review-recorded', 'verdict': payload['status'], 'result': str(output),
            'next': 'status or checked deliver; review records alone do not establish final acceptance'}


def status(flow):
    import writing_run as native
    import writing_lifecycle as lifecycle
    import writing_execution as execution
    paths = flow['paths']
    with native.session(paths['native']) as state:
        if not state['preparations']:
            return {'status': 'in-progress', 'next': 'prepare: seal character notes, or use the contract exemption'}
        if not state['drafts']:
            return {'status': 'in-progress', 'next': 'draft: register actual manuscript and complete-unit observations'}
        record = native.check_records(state)
        reviews = native.latest_reviews(state)
        pending, decisions = native.editorial_review_state(state) if hasattr(native, 'editorial_review_state') else ([], [])
    with lifecycle.session(paths['lifecycle']) as life:
        batch = life['rounds'][-1] if life['rounds'] else None
        rounds = len(life['rounds'])
        presentation = life.get('presentations', [])[-1] if life.get('presentations') else None
    if pending and any(not any(all(d.get(k) == f.get(k) for k in ('role', 'finding_id', 'reviewer_receipt'))
                              for d in decisions) for f in pending):
        action = 'author-choice, then finish-review in the same batch'
    elif batch and batch['verdict'] is None:
        with execution.task(paths['lifecycle']) as task:
            jobs = task['batches'][str(batch['round'])]['jobs']
            captured = len(jobs) == len(execution.policy()['roles']) and all(j['status'] == 'captured' for j in jobs.values())
        action = 'finish-review' if captured else 'invoke or resume the actual host bridge; never duplicate an uncertain launch'
    elif presentation and presentation['reading_effect'] != 'unchanged':
        action = 'register and review a new literary version for the changed or uncertain presentation; do not reuse old acceptance'
    elif not {'clean', 'comparison'} <= set(reviews):
        action = 'self-review: complete clean then comparison for the current version'
    elif record['blockers']:
        action = 'resolve native blockers and decide; existing records do not authorize completion'
        if rounds == execution.policy()['max_rounds'] and batch and batch['verdict'] == 'fail':
            action = 'checked deliver --draft only if native guards allow it; explain unresolved issues and ask for direction, no fourth round'
    else:
        action = execution.next_step(paths['lifecycle'])['next']
        if action == 'checked-native-delivery':
            action = 'checked deliver; recorded reviewer pass is not a fresh checked acceptance'
    return {'status': 'in-progress', 'next': action, 'native_blockers': record['blockers'],
            'rounds': rounds, 'pending_editorial': pending, 'completion_verified': False}


def operate(flow, args):
    import writing_run as native
    import writing_lifecycle as lifecycle
    import writing_execution as execution
    if args.command == 'prepare':
        return prepare(flow, args)
    if args.command == 'draft':
        return draft(flow, args)
    if args.command == 'self-review':
        return self_review(flow, args)
    if args.command in ('decide', 'author-choice'):
        with native.session(flow['paths']['native'], True) as state:
            function = native.decide if args.command == 'decide' else native.decide_editorial
            return function(state, load(args.file))
    if args.command == 'candidate':
        return candidate(flow, args)
    if args.command == 'finish-review':
        return finish_review(flow, args)
    if args.command == 'presentation':
        return lifecycle.register_presentation(flow['paths']['lifecycle'], args.record)
    if args.command == 'status':
        return status(flow)
    arguments = [args.command, flow['paths']['native']]
    if args.command == 'deliver':
        arguments += ['--to', str(Path(args.to).absolute())]
    elif args.final:
        arguments += ['--final', str(Path(args.final).absolute())]
    if args.draft:
        arguments.append('--draft')
    return json.loads(execution.deliver(flow['paths']['lifecycle'], arguments))


def parser():
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest='command', required=True)
    for name in ('start', 'prepare', 'draft', 'self-review', 'decide', 'author-choice',
                 'candidate', 'finish-review', 'presentation', 'status', 'check', 'deliver'):
        child = commands.add_parser(name)
        child.add_argument('task')
        if name == 'start':
            child.add_argument('--request', required=True)
            child.add_argument('--task-id', required=True)
            child.add_argument('--registry')
        elif name == 'prepare':
            source = child.add_mutually_exclusive_group()
            source.add_argument('--character'); source.add_argument('--record')
            child.add_argument('--id', default='character-v1')
            child.add_argument('--reason', required=True)
            child.add_argument('--timing', choices=('prewrite', 'during', 'retrospective'), default='prewrite')
        elif name == 'draft':
            child.add_argument('--id', required=True); child.add_argument('--file', required=True)
            units = child.add_mutually_exclusive_group()
            units.add_argument('--units'); units.add_argument('--record')
        elif name == 'self-review':
            child.add_argument('--clean'); child.add_argument('--comparison')
        elif name in ('decide', 'author-choice'):
            child.add_argument('--file', required=True)
        elif name == 'candidate':
            child.add_argument('--report'); child.add_argument('--assessment'); child.add_argument('--geometry')
            child.add_argument('--stage', choices=('during', 'after'), default='after')
        elif name == 'finish-review':
            child.add_argument('--results')
        elif name == 'presentation':
            child.add_argument('--record', required=True)
        elif name in ('deliver', 'check'):
            child.add_argument('--draft', action='store_true')
            if name == 'deliver':
                child.add_argument('--to', required=True)
            else:
                child.add_argument('--final')
    return cli


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = parser().parse_args(argv)
    task = Path(args.task).absolute()
    try:
        need(not task.is_symlink(), 'Task directory must not be a symbolic link')
        task = task.resolve()
        if args.command == 'start' and not (task / 'workflow.json').exists():
            flow = create_workflow(args, task)
        else:
            flow = read_workflow(task)
        import runtime_bundle
        pinned = runtime_bundle.verify(flow['runtime'])
        if pinned != ROOT:
            return subprocess.run([sys.executable, '-B', str(pinned / 'scripts/writer.py'), *argv]).returncode
        with locked(task):
            if args.command == 'start':
                result = initialize(flow, args)
            else:
                ready(flow)
                result = operate(flow, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if result.get('status') in ('blocked', 'error') else 0
    except (ImportError, OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
        print(json.dumps({'status': 'incomplete', 'reason': str(error),
                          'next': 'Preserve this task and registry. Resume its pinned workflow after resolving the reported input; do not reset rounds.'},
                         ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
