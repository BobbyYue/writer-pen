// Run through the host's code tool with the real tools object, not a model-written receipt.
// No Node or network dependency. All model choices inherit the calling host.
async function runWritingHost(tools, options) {
  const required = ['exec_command', 'write_stdin', 'multi_agent_v1__spawn_agent', 'multi_agent_v1__wait_agent', 'multi_agent_v1__close_agent'];
  for (const name of required) if (typeof tools[name] !== 'function') throw new Error('Required native host capability is unavailable: ' + name);
  const quote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
  const python = options.python || 'python3';
  const script = options.skillRoot + '/scripts/writing_host.py';
  const collect = async result => {
    let output = result.output || '';
    while (result.session_id) {
      result = await tools.write_stdin({session_id: result.session_id, chars: '', yield_time_ms: 1000, max_output_tokens: 2000});
      output += result.output || '';
    }
    if (result.exit_code !== 0) throw new Error('Managed native bridge rejected the operation; inspect its private records');
    return JSON.parse(output);
  };
  const command = async (args, input) => {
    const parts = [python, '-B', script, ...args];
    let cmd = parts.map(quote).join(' ');
    let transportPath;
    try {
      const serialized = input === undefined ? undefined : JSON.stringify(input);
      const fileInput = serialized !== undefined && typeof tools.apply_patch === 'function';
      if (fileInput) {
        const reserve = 'import json,os,sys,tempfile; fd,p=tempfile.mkstemp(prefix=".writing-host-transport-",suffix=".json",dir=sys.argv[1]); os.close(fd); print(json.dumps({"path":p}))';
        const reserved = await collect(await tools.exec_command({cmd: quote(python) + ' -c ' + quote(reserve) + ' ' + quote(options.run), yield_time_ms: 1000, max_output_tokens: 2000}));
        transportPath = reserved.path;
        const patched = await tools.apply_patch('*** Begin Patch\n*** Update File: ' + transportPath + '\n@@\n+' + serialized + '\n*** End Patch');
        if (patched && patched.isError) throw new Error('Native bridge could not save its private transport input');
        const forward = 'import subprocess,sys\nwith open(sys.argv[1], "rb") as source:\n p=subprocess.run(sys.argv[2:],stdin=source,text=True,encoding="utf-8",capture_output=True)\nsys.stdout.write(p.stdout); sys.stderr.write(p.stderr); sys.exit(p.returncode)';
        cmd = quote(python) + ' -c ' + quote(forward) + ' ' + quote(transportPath) + ' ' + cmd;
      } else if (serialized !== undefined) {
        // Hosts without apply_patch retain only the bounded, small-input PTY path.
        if (serialized.length > 8192) throw new Error('Large native input requires apply_patch; preserve the live agent and resume this task with file transport');
        cmd = quote(python) + ' -c ' + quote('import subprocess,sys,termios; a=termios.tcgetattr(0); a[3]&=~(termios.ECHO|termios.ICANON); termios.tcsetattr(0,termios.TCSANOW,a); p=subprocess.run(sys.argv[1:],input=sys.stdin.readline(),text=True,capture_output=True); sys.stdout.write(p.stdout); sys.stderr.write(p.stderr); sys.exit(p.returncode)') + ' ' + cmd;
      }
      let result = await tools.exec_command({cmd, tty: serialized !== undefined && !fileInput, yield_time_ms: 1000, max_output_tokens: 2000});
      if (serialized !== undefined && !fileInput) {
        if (!result.session_id) throw new Error('Native bridge input channel failed');
        const prefix = result.output || '';
        result = await tools.write_stdin({session_id: result.session_id, chars: serialized + '\n', yield_time_ms: 1000, max_output_tokens: 2000});
        result = {...result, output: prefix + (result.output || '')};
      }
      return await collect(result);
    } catch (error) {
      error.transportPath = transportPath;
      throw error;
    }
  };
  const args = ['prepare', options.run, '--packets', options.packets];
  if (options.nativeRun) args.push('--native-run', options.nativeRun);
  const active = new Map();
  let failure = null;
  const review = async request => {
      const promptResult = await tools.exec_command({cmd: quote(python) + ' -c ' + quote('import pathlib,sys,json; print(json.dumps({"text":pathlib.Path(sys.argv[1]).read_text()}))') + ' ' + quote(request.prompt), max_output_tokens: 60000});
      if (promptResult.exit_code !== 0 || promptResult.original_token_count > 59000) throw new Error('Prepared review input could not be read completely');
      const spawnArguments = {fork_context: false, message: JSON.parse(promptResult.output).text};
      let spawn;
      if (request.status === 'started') {
        spawn = request.spawn;
      } else {
        if (request.status !== 'prepared') throw new Error('Uncertain prior launch; do not duplicate a possibly running reviewer');
        await command(['claim', options.run, '--request', request.attempt_id]);
        try { spawn = await tools.multi_agent_v1__spawn_agent(spawnArguments); }
        catch (error) {
          await command(['launch-failed', options.run, '--request', request.attempt_id],
                        {name: error.name || 'Error', message: String(error.message || error), code: error.code || null});
          throw new Error('Native launch failed without an agent receipt; inspect the saved error and confirm no agent exists before recover-launch');
        }
        try { await command(['started', options.run, '--request', request.attempt_id], spawn); }
        catch (error) {
          error.recovery = {run: options.run, requestId: request.attempt_id, agentId: spawn.agent_id, spawn, transportPath: error.transportPath};
          error.message += '; preserve agent ' + spawn.agent_id + ' and error.recovery.spawn' +
            (error.transportPath ? '; keep transport file ' + error.transportPath : '') + '; do not relaunch';
          throw error;
        }
      }
      // No short polling: preserve the same live reviewer across timeout waits.
      let returned;
      let waits = 0;
      do {
        returned = await tools.multi_agent_v1__wait_agent({targets: [spawn.agent_id], timeout_ms: 120000});
      } while (returned.timed_out && ++waits < 3);
      if (returned.timed_out) throw new Error('Review is still running; resume the same stored agent instead of starting another');
      const raw = {arguments: spawnArguments, spawn, wait: returned};
      let imported;
      try { imported = await command(['finish', options.run, '--request', request.attempt_id], raw); }
      catch (error) {
        error.recovery = {run: options.run, requestId: request.attempt_id, agentId: spawn.agent_id, raw, transportPath: error.transportPath};
        error.message += '; agent ' + spawn.agent_id + ' remains open; preserve error.recovery.raw' +
          (error.transportPath ? ' and transport file ' + error.transportPath : '') + '; recover the same request without relaunch';
        throw error;
      }
      await tools.multi_agent_v1__close_agent({target: spawn.agent_id});
      return imported;
  };
  try {
    for (;;) {
      if (!failure) {
        const batch = await command(args);
        if (batch.complete) {
          const remaining = await Promise.all(active.values());
          const failed = remaining.find(value => value.error);
          if (failed) throw failed.error;
          return {status: 'captured', round: batch.round, results: batch.results};
        }
        for (const request of batch.requests) {
          if (active.has(request.attempt_id)) continue;
          const result = review(request).then(
            value => ({id: request.attempt_id, value}),
            error => ({id: request.attempt_id, error})
          );
          active.set(request.attempt_id, result);
        }
      }
      if (!active.size) throw failure || new Error('No runnable request; native dependency or transport is blocked');
      // Release dependents after each collected return, not after the slowest peer.
      const completed = await Promise.race(active.values());
      active.delete(completed.id);
      if (completed.error) failure = failure || completed.error;
    }
  } catch (error) {
    await Promise.all(active.values());
    throw error;
  }
}
