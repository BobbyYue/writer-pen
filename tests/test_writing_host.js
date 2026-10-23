// Offline protocol regression. These tool returns are synthetic, not model evidence.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const os = require('node:os');
const {spawnSync} = require('node:child_process');
const scope = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../scripts/writing_host.js'), 'utf8'), scope);

async function probe(rejectSpawn, alreadyStarted = false) {
  let state = alreadyStarted ? 'started' : 'prepared', pending = null, split = false, spawned = 0, closed = 0, done = false;
  const answer = value => ({output: JSON.stringify(value), exit_code: 0});
  const tools = {
    async exec_command({cmd}) {
      if (cmd.includes("'prepare'")) return answer({round: 1, complete: done, results: done ? {reader: '/synthetic/result.json'} : {},
        requests: done ? [] : [{role: 'reader', attempt_id: 'fixture', status: state, prompt: '/synthetic/prompt',
          spawn: state === 'started' ? {agent_id: 'actual-fixture-agent'} : null}]});
      if (cmd.includes("'claim'")) {
        state = 'launching'; split = true;
        return {output: '{"status":"launching"}', session_id: 1};
      }
      for (const name of ['started', 'finish', 'launch-failed']) {
        if (cmd.includes("'" + name + "'")) { pending = name; return {output: '', session_id: 2}; }
      }
      return answer({text: 'Synthetic isolated prompt'});
    },
    async write_stdin({chars}) {
      if (split) { split = false; return {output: '', exit_code: 0}; }
      const value = JSON.parse(chars);
      if (pending === 'started') { assert.equal(value.agent_id, 'actual-fixture-agent'); state = 'started'; }
      if (pending === 'finish') { assert.equal(value.arguments.fork_context, false); done = true; state = 'captured'; }
      if (pending === 'launch-failed') state = 'launch-uncertain';
      pending = null;
      return answer({status: state});
    },
    async multi_agent_v1__spawn_agent(args) {
      assert.equal(args.fork_context, false); spawned++;
      if (rejectSpawn) throw new Error('SYNTHETIC rejection with no receipt');
      return {agent_id: 'actual-fixture-agent', nickname: 'Fixture'};
    },
    async multi_agent_v1__wait_agent() {
      return {status: {'actual-fixture-agent': {completed: '{"verdict":"pass"}'}}, timed_out: false};
    },
    async multi_agent_v1__close_agent() { closed++; return {}; }
  };
  const options = {skillRoot: '/synthetic/skill', run: '/synthetic/run', packets: '/synthetic/packets'};
  if (rejectSpawn) {
    await assert.rejects(scope.runWritingHost(tools, options), /confirm no agent/);
    assert.equal(state, 'launch-uncertain');
    await assert.rejects(scope.runWritingHost(tools, options), /Uncertain prior launch/);
    assert.equal(spawned, 1);
  } else {
    const result = await scope.runWritingHost(tools, options);
    assert.equal(result.status, 'captured');
    assert.equal(spawned, alreadyStarted ? 0 : 1); assert.equal(closed, 1);
  }
}

async function dependencyProbe() {
  const roles = ['no-context', 'readability', 'structure-visual', 'source-reliability'];
  const jobs = Object.fromEntries(roles.map(role => [role, {role, attempt_id: role, status: 'prepared', prompt: '/fixture/' + role}]));
  const events = [], sessions = new Map(), launches = {};
  let serial = 100, release;
  const sourceStarted = new Promise(resolve => { release = resolve; });
  const answer = value => ({output: JSON.stringify(value), exit_code: 0});
  const tools = {
    async exec_command({cmd}) {
      if (cmd.includes("'prepare'")) {
        const complete = roles.every(role => jobs[role].status === 'captured');
        const requests = roles.filter(role => jobs[role].status !== 'captured' &&
          (role !== 'source-reliability' || jobs['no-context'].status === 'captured')).map(role => jobs[role]);
        return answer({round: 1, complete, requests, results: {}});
      }
      const operation = ['claim', 'started', 'finish', 'launch-failed'].find(name => cmd.includes("'" + name + "'"));
      if (operation) {
        const role = cmd.match(/'--request'\s+'([^']+)'/)[1];
        if (operation === 'claim') {
          assert.equal(jobs[role].status, 'prepared'); jobs[role].status = 'launching'; return answer({});
        }
        const id = serial++; sessions.set(id, {operation, role});
        return {output: '', session_id: id};
      }
      const role = roles.find(role => cmd.includes('/fixture/' + role));
      assert.ok(role); return answer({text: 'ROLE:' + role});
    },
    async write_stdin({session_id, chars}) {
      const {operation, role} = sessions.get(session_id);
      sessions.delete(session_id);
      const value = JSON.parse(chars);
      if (operation === 'started') { jobs[role].status = 'started'; jobs[role].spawn = value; }
      if (operation === 'finish') { jobs[role].status = 'captured'; events.push('captured:' + role); }
      return answer({});
    },
    async multi_agent_v1__spawn_agent(args) {
      assert.equal(args.fork_context, false);
      const role = args.message.slice(5);
      launches[role] = (launches[role] || 0) + 1;
      events.push('started:' + role);
      if (role === 'source-reliability') release();
      return {agent_id: role};
    },
    async multi_agent_v1__wait_agent({targets}) {
      const role = targets[0];
      if (role === 'readability' || role === 'structure-visual') await sourceStarted;
      return {status: {[role]: {completed: '{"status":"pass"}'}}, timed_out: false};
    },
    async multi_agent_v1__close_agent({target}) { events.push('closed:' + target); return {}; }
  };
  let timer;
  try {
    const timedOut = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Dependency scheduler stalled behind unrelated reviewers')), 5000); });
    await Promise.race([scope.runWritingHost(tools, {skillRoot: '/fixture/skill', run: '/fixture/run', packets: '/fixture/packets'}), timedOut]);
  } finally { clearTimeout(timer); }
  assert.ok(events.indexOf('started:source-reliability') < events.indexOf('captured:structure-visual'));
  assert.ok(events.indexOf('captured:no-context') < events.indexOf('started:source-reliability'));
  assert.deepEqual(Object.values(launches), [1, 1, 1, 1]);
  assert.equal(events.filter(event => event.startsWith('closed:')).length, 4);
}

// Synthetic host state, but real files, shell quoting, Python subprocess and stdin.
// The opaque completion below is deliberately not a fabricated review or PASS.
function fileHost() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "writing-host-'$;-"));
  const run = path.join(root, "run ' with spaces;$()"), skillRoot = path.join(root, "skill ' with spaces");
  fs.mkdirSync(run);
  fs.mkdirSync(path.join(skillRoot, 'scripts'), {recursive: true});
  const prompt = 'PROMPT_MARKER \u4e2d\u6587 "quoted" \\ \n'.repeat(12000);
  const spawn = {agent_id: 'synthetic-file-agent', nickname: 'Fixture', extra: {unchanged: true}};
  const wait = {status: {[spawn.agent_id]: {completed: 'OPAQUE_RAW_MARKER \u4e2d\u6587 " \\ \r\n\u2028'.repeat(50000),
    extra: [null, false, 0]}}, timed_out: false, transport_metadata: {preserve: 'verbatim'}};
  const expected = {arguments: {fork_context: false, message: prompt}, spawn, wait};
  const statePath = path.join(run, 'state.json');
  const promptPath = path.join(run, 'prompt.txt');
  fs.writeFileSync(promptPath, prompt);
  fs.writeFileSync(statePath, JSON.stringify({status: 'prepared', round: 2, claims: 0}));
  fs.writeFileSync(path.join(skillRoot, 'scripts/writing_host.py'), `
import json, pathlib, sys
operation, run = sys.argv[1], pathlib.Path(sys.argv[2])
state_path = run / 'state.json'
state = json.loads(state_path.read_text())
if operation == 'prepare':
    done = state['status'] == 'captured'
    result = {'round': state['round'], 'complete': done, 'results': {}, 'requests': [] if done else [
        {'attempt_id': 'same-request', 'role': 'reader', 'status': state['status'],
         'prompt': str(run / 'prompt.txt'), 'spawn': state.get('spawn')}]}
elif operation == 'claim':
    assert state['status'] == 'prepared'
    state.update(status='launching', claims=state['claims'] + 1)
    result = {'status': 'launching'}
else:
    body = sys.stdin.buffer.read()
    value = json.loads(body)
    if operation == 'started':
        assert state['status'] == 'launching'
        state.update(status='started', spawn=value)
    elif operation == 'finish':
        assert state['status'] == 'started'
        (run / 'host-return.json').write_bytes(body)
        state['status'] = 'blocked' if state.get('reject_import') else 'captured'
    else:
        raise AssertionError(operation)
    result = {'status': state['status']}
state_path.write_text(json.dumps(state))
if state['status'] == 'blocked':
    sys.exit(1)
print(json.dumps(result))
`);
  const events = [], inputs = [], commands = [], sessions = new Map();
  let spawned = 0, closed = 0, waited = 0, serial = 1000;
  const faults = {};
  const tools = {
    async exec_command({cmd, tty}) {
      commands.push(cmd);
      assert.ok(cmd.length < 16000, 'Payload must not be embedded in the command line');
      assert.ok(!cmd.includes('PROMPT_MARKER') && !cmd.includes('OPAQUE_RAW_MARKER'));
      assert.ok(!tty, 'File transport must not allocate a PTY');
      const operation = ['prepare', 'claim', 'started', 'finish'].find(name => cmd.includes("'" + name + "'"));
      if (faults.exec === operation && operation) {
        events.push('rejected:' + operation);
        return {output: '', exit_code: 1};
      }
      const result = spawnSync('/bin/sh', ['-c', cmd], {encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
      if (result.error) throw result.error;
      if (result.status !== 0 && operation !== 'finish') throw new Error(result.stderr);
      if (operation) events.push(operation);
      if (operation === 'finish' && result.status === 0) {
        assert.equal(fs.readFileSync(path.join(run, 'host-return.json'), 'utf8'), JSON.stringify(expected) + '\n');
      }
      const output = result.stdout + result.stderr;
      if (result.status !== 0) return {output, exit_code: result.status};
      // Exercise output accumulation on the new file-input command path too.
      if (operation === 'finish') {
        const id = serial++;
        sessions.set(id, {output: output.slice(5), exit_code: 0});
        return {output: output.slice(0, 5), session_id: id};
      }
      return {output, exit_code: 0};
    },
    async write_stdin({session_id, chars}) {
      assert.equal(chars, '', 'No input payload may travel through write_stdin');
      const result = sessions.get(session_id);
      assert.ok(result); sessions.delete(session_id);
      return result;
    },
    async apply_patch(patch) {
      const lines = patch.split('\n');
      assert.equal(lines[0], '*** Begin Patch');
      assert.ok(lines[1].startsWith('*** Update File: '));
      assert.equal(lines[2], '@@');
      assert.equal(lines[4], '*** End Patch');
      const file = lines[1].slice('*** Update File: '.length);
      assert.equal(path.dirname(file), run);
      assert.match(path.basename(file), /^\.writing-host-transport-.+\.json$/);
      assert.equal(fs.statSync(file).mode & 0o777, 0o600, 'Reserve a new private file before patching');
      assert.equal(fs.readFileSync(file, 'utf8'), '', 'Never reuse or overwrite a prior transport');
      assert.equal(lines[3][0], '+');
      const text = lines[3].slice(1), value = JSON.parse(text);
      inputs.push({file, text, value});
      const operation = value.wait ? 'finish' : 'started';
      if (faults.patch === operation) throw new Error('SYNTHETIC patch rejected before saving');
      if (process.env.WRITING_HOST_REAL_PATCH === '1') {
        const applied = spawnSync('apply_patch', [], {input: patch, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024});
        if (applied.error) throw applied.error;
        assert.equal(applied.status, 0, applied.stderr);
      } else {
        fs.writeFileSync(file, text + '\n');
      }
      assert.equal(fs.statSync(file).mode & 0o777, 0o600);
      events.push('saved:' + operation);
      if (faults.patchReply === operation) return {isError: true};
      return {};
    },
    async multi_agent_v1__spawn_agent(args) {
      assert.equal(JSON.stringify(args), JSON.stringify(expected.arguments));
      spawned++; events.push('spawn'); return spawn;
    },
    async multi_agent_v1__wait_agent(args) {
      assert.equal(JSON.stringify(args), JSON.stringify({targets: [spawn.agent_id], timeout_ms: 120000}));
      waited++; return wait;
    },
    async multi_agent_v1__close_agent({target}) {
      assert.equal(target, spawn.agent_id);
      assert.equal(fs.readFileSync(path.join(run, 'host-return.json'), 'utf8'), JSON.stringify(expected) + '\n',
        'Raw must be saved and imported before closing the agent');
      closed++; events.push('close'); return {};
    }
  };
  return {tools, faults, events, inputs, commands, expected, statePath, run,
    options: {skillRoot, run, packets: path.join(root, "packets ' with spaces.json")},
    counts: () => ({spawned, closed, waited}),
    cleanup: () => fs.rmSync(root, {recursive: true, force: true})};
}

async function fileTransportProbe(fault) {
  const host = fileHost();
  try {
    if (fault) host.faults[fault] = 'finish';
    let saved;
    if (fault) {
      await assert.rejects(scope.runWritingHost(host.tools, host.options), error => {
        saved = error.recovery;
        assert.equal(saved.agentId, host.expected.spawn.agent_id);
        assert.equal(saved.requestId, 'same-request');
        assert.equal(saved.run, host.run);
        assert.equal(saved.raw.wait, host.expected.wait);
        assert.equal(JSON.stringify(saved.raw), JSON.stringify(host.expected));
        assert.ok(fs.existsSync(saved.transportPath));
        assert.ok(error.message.includes(saved.agentId) && error.message.includes(saved.transportPath));
        return true;
      });
      assert.deepEqual(host.counts(), {spawned: 1, closed: 0, waited: 1});
      assert.equal(JSON.parse(fs.readFileSync(host.statePath)).status, 'started');
      const originalBytes = fs.readFileSync(saved.transportPath);
      if (fault !== 'patch') assert.equal(originalBytes.toString(), JSON.stringify(host.expected) + '\n');
      delete host.faults[fault];
      const resumed = await scope.runWritingHost(host.tools, host.options);
      assert.equal(resumed.round, 2);
      assert.deepEqual(fs.readFileSync(saved.transportPath), originalBytes, 'Recovery must not overwrite the original file');
    } else {
      const result = await scope.runWritingHost(host.tools, host.options);
      assert.equal(result.status, 'captured'); assert.equal(result.round, 2);
    }
    assert.equal(host.counts().spawned, 1, 'Recovery must not respawn a known agent');
    assert.equal(host.counts().closed, 1);
    assert.equal(JSON.parse(fs.readFileSync(host.statePath)).claims, 1);
    assert.equal(new Set(host.inputs.map(input => input.file)).size, host.inputs.length);
    const rawInputs = host.inputs.filter(input => input.value.wait);
    assert.ok(rawInputs[0].text.length > 1024 * 1024);
    for (const input of rawInputs) assert.equal(input.text, JSON.stringify(host.expected));
    assert.ok(host.events.indexOf('saved:finish') < host.events.indexOf('close'));
    assert.ok(host.events.indexOf('finish') < host.events.indexOf('close'));
  } finally { host.cleanup(); }
}

async function importFailureProbe() {
  const host = fileHost();
  try {
    const state = JSON.parse(fs.readFileSync(host.statePath));
    state.reject_import = true;
    fs.writeFileSync(host.statePath, JSON.stringify(state));
    await assert.rejects(scope.runWritingHost(host.tools, host.options), error => {
      assert.equal(error.recovery.agentId, host.expected.spawn.agent_id);
      assert.equal(fs.readFileSync(error.recovery.transportPath, 'utf8'), JSON.stringify(host.expected) + '\n');
      return true;
    });
    assert.deepEqual(host.counts(), {spawned: 1, closed: 0, waited: 1});
    assert.equal(JSON.parse(fs.readFileSync(host.statePath)).status, 'blocked');
    assert.equal(JSON.parse(fs.readFileSync(host.statePath)).round, 2);
  } finally { host.cleanup(); }
}

async function startedSaveFailureProbe() {
  const host = fileHost();
  try {
    host.faults.exec = 'started';
    let saved;
    await assert.rejects(scope.runWritingHost(host.tools, host.options), error => {
      saved = error.recovery;
      assert.equal(saved.agentId, host.expected.spawn.agent_id);
      assert.equal(saved.spawn, host.expected.spawn);
      assert.equal(fs.readFileSync(saved.transportPath, 'utf8'), JSON.stringify(saved.spawn) + '\n');
      return true;
    });
    assert.deepEqual(host.counts(), {spawned: 1, closed: 0, waited: 0});
    await assert.rejects(scope.runWritingHost(host.tools, host.options), /Uncertain prior launch/);
    assert.equal(host.counts().spawned, 1);
    // Same-request operator recovery uses the actual receipt, never recover-launch.
    const recovered = spawnSync('python3', ['-B', path.join(host.options.skillRoot, 'scripts/writing_host.py'),
      'started', host.run, '--request', saved.requestId], {input: fs.readFileSync(saved.transportPath), encoding: 'utf8'});
    assert.equal(recovered.status, 0, recovered.stderr);
    delete host.faults.exec;
    assert.equal((await scope.runWritingHost(host.tools, host.options)).round, 2);
    assert.deepEqual(host.counts(), {spawned: 1, closed: 1, waited: 1});
  } finally { host.cleanup(); }
}

async function legacyLargeReturnProbe() {
  let state = 'prepared', pending, spawned = 0, closed = 0, finishCalled = false;
  const wait = {status: {legacy: {completed: 'Opaque synthetic return'.repeat(10000)}}, timed_out: false};
  const answer = value => ({output: JSON.stringify(value), exit_code: 0});
  const tools = {
    async exec_command({cmd}) {
      if (cmd.includes("'prepare'")) return answer({complete: false, round: 1, requests: [
        {status: state, attempt_id: 'legacy-request', prompt: '/synthetic/prompt', spawn: {agent_id: 'legacy'}}]});
      if (cmd.includes("'claim'")) { state = 'launching'; return answer({}); }
      if (cmd.includes("'started'")) { pending = 'started'; return {output: '', session_id: 1}; }
      if (cmd.includes("'finish'")) { finishCalled = true; throw new Error('Large raw reached the PTY'); }
      return answer({text: 'Small legacy prompt'});
    },
    async write_stdin({chars}) {
      assert.equal(pending, 'started');
      assert.equal(JSON.parse(chars).agent_id, 'legacy'); state = 'started'; return answer({});
    },
    async multi_agent_v1__spawn_agent() { spawned++; return {agent_id: 'legacy'}; },
    async multi_agent_v1__wait_agent() { return wait; },
    async multi_agent_v1__close_agent() { closed++; }
  };
  for (let attempt = 0; attempt < 2; attempt++) {
    await assert.rejects(scope.runWritingHost(tools, {skillRoot: '/synthetic', run: '/synthetic/run', packets: '/synthetic/packets'}), error => {
      assert.match(error.message, /requires apply_patch/);
      assert.equal(error.recovery.agentId, 'legacy');
      assert.equal(error.recovery.raw.wait, wait);
      assert.equal(error.recovery.transportPath, undefined);
      return true;
    });
  }
  assert.equal(state, 'started'); assert.equal(spawned, 1); assert.equal(closed, 0); assert.equal(finishCalled, false);
}

(async () => {
  await probe(false);
  await probe(true);
  await probe(false, true);
  await dependencyProbe();
  await fileTransportProbe();
  await fileTransportProbe('patch');
  await fileTransportProbe('patchReply');
  await fileTransportProbe('exec');
  await importFailureProbe();
  await startedSaveFailureProbe();
  await legacyLargeReturnProbe();
  process.stdout.write('PASS: 11 protocol probes; real file/subprocess large-payload transport, unchanged raw, private unique files, safe quoting, save/import failure retention, no respawn on recovery, legacy fallback, split output, uncertain launch and dependency scheduling\n');
})().catch(error => { process.stderr.write(String(error.stack)); process.exitCode = 1; });
