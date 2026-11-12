// One bounded native proof. No Python/backend edits, real credentials or cloud calls.
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createServer} from 'node:http';
import {createConnection, createServer as tcpServer} from 'node:net';
import {mkdtemp, mkdir, readFile, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const image = 'otel/opentelemetry-collector-contrib:0.165.0@sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea';
const output = await mkdtemp(resolve(tmpdir(), 'peerly-archive-'));
const canary = 'SYNTHETIC_PRIVATE_ARCHIVE_CANARY';
const objects = new Map();
let accepting = false;
let rejected = 0;
let overwrites = 0;
let fixtureError;
let collector;
let extracted;
let deadline;
const cleanEnv = {
  PATH: process.env.PATH, HOME: output, TZ: 'UTC', GOMEMLIMIT: '224MiB',
  AWS_ACCESS_KEY_ID: 'synthetic-only', AWS_SECRET_ACCESS_KEY: 'synthetic-only-not-a-credential',
  AWS_SHARED_CREDENTIALS_FILE: '/dev/null', AWS_CONFIG_FILE: '/dev/null',
  AWS_EC2_METADATA_DISABLED: 'true', AWS_REQUEST_CHECKSUM_CALCULATION: 'WHEN_REQUIRED',
  PEERLY_ENVIRONMENT: 'test', PEERLY_RELEASE: 'synthetic-archive', PEERLY_AI_RELEASE: '',
  LOKI_OTLP_ENDPOINT: 'http://127.0.0.1:1', LOKI_AUTHORIZATION: '', LOKI_TENANT_ID: '',
  PEERLY_ARCHIVE_S3_REGION: 'us-east-1', PEERLY_ARCHIVE_S3_ENDPOINT: 'http://127.0.0.1:1',
  PEERLY_ARCHIVE_S3_BUCKET: 'synthetic', PEERLY_ARCHIVE_S3_PREFIX: 'peerly/test',
  PEERLY_ARCHIVE_S3_FORCE_PATH_STYLE: 'true',
};
function docker(args) {
  const result = spawnSync('docker', args, {encoding: 'utf8', timeout: 20000});
  assert.equal(result.status, 0, `docker ${args[0]} failed`);
  return result.stdout.trim();
}
async function unusedPort() {
  const server = tcpServer();
  await new Promise((done, fail) => {server.once('error', fail); server.listen(0, '127.0.0.1', done);});
  const port = server.address().port;
  await new Promise(done => server.close(done));
  return port;
}
async function waitFor(predicate, label, seconds = 20) {
  const until = Date.now() + seconds * 1000;
  while (Date.now() < until) {
    if (fixtureError) throw fixtureError;
    if (await predicate()) return;
    await new Promise(done => setTimeout(done, 100));
  }
  throw new Error(`Timed out: ${label}`);
}
const sink = createServer(async (request, response) => {
  try {
    const chunks = [];
    let size = 0;
    for await (const chunk of request) {
      size += chunk.length;
      assert(size <= 2097152, 'Synthetic transport exceeded bound');
      chunks.push(chunk);
    }
    if (request.method === 'PUT') {
      if (!accepting) {
        rejected++;
        response.writeHead(503, {'Content-Type': 'application/xml'});
        response.end('<Error><Code>ServiceUnavailable</Code></Error>');
        return;
      }
      let body = Buffer.concat(chunks);
      if (request.headers['content-encoding']?.includes('aws-chunked')) {
        const decoded = [];
        while (true) {
          const end = body.indexOf('\r\n');
          assert(end >= 0, 'Missing synthetic AWS chunk boundary');
          const length = Number.parseInt(body.subarray(0, end).toString().split(';')[0], 16);
          assert(Number.isSafeInteger(length) && length >= 0 && length <= 2097152);
          if (length === 0) break;
          decoded.push(body.subarray(end + 2, end + 2 + length));
          body = body.subarray(end + 2 + length + 2);
        }
        body = Buffer.concat(decoded);
      }
      const json = gunzipSync(body, {maxOutputLength: 2097152}).toString();
      assert(!json.includes(canary), 'Privacy sentinel escaped sanitizer');
      const parsed = JSON.parse(json);
      assert(parsed.resourceLogs || parsed.resourceSpans, 'Not native OTLP JSON');
      assert(request.url.startsWith('/synthetic/peerly/test/'), 'Resource-controlled routing escaped');
      if (objects.has(request.url)) overwrites++;
      objects.set(request.url, {body, json, parsed});
      response.writeHead(200, {'ETag': '"synthetic"'});
    } else response.writeHead(200, {'Content-Type': 'application/x-protobuf'});
    response.end();
  } catch (error) {
    fixtureError = error;
    response.writeHead(500);
    response.end();
  }
});
await new Promise(done => sink.listen(0, '127.0.0.1', done));
function native(args, name) {
  return new Promise((done, fail) => {
    const child = spawn(resolve(output, 'otelcol-contrib'), args, {env: cleanEnv});
    const chunks = [];
    child.stderr.on('data', chunk => chunks.push(chunk));
    child.stdout.on('data', chunk => chunks.push(chunk));
    child.once('error', fail);
    child.once('exit', async code => {
      await writeFile(resolve(output, `${name}.log`), Buffer.concat(chunks));
      code === 0 ? done() : fail(new Error(`Native ${name} failed; inspect artifact`));
    });
  });
}
async function launch(args, name) {
  const child = spawn(resolve(output, 'otelcol-contrib'), args, {env: cleanEnv});
  const chunks = [];
  child.stderr.on('data', chunk => chunks.push(chunk));
  child.stdout.on('data', chunk => chunks.push(chunk));
  child.once('error', error => {fixtureError = error;});
  child.once('exit', () => {void writeFile(resolve(output, `${name}.log`), Buffer.concat(chunks));});
  return child;
}
async function stop(child, signal = 'SIGTERM') {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const ended = new Promise(done => child.once('exit', done));
  child.kill(signal);
  await ended;
}
try {
  deadline = setTimeout(() => {fixtureError = new Error('Proof exceeded90s'); collector?.kill('SIGKILL');}, 90000);
  // Extract the locally present immutable image's binary; do not pull or run a host-privileged container.
  docker(['image', 'inspect', image]);
  extracted = docker(['create', '--network=none', image]);
  docker(['cp', `${extracted}:/otelcol-contrib`, resolve(output, 'otelcol-contrib')]);
  docker(['rm', extracted]);
  extracted = undefined;
  const port = sink.address().port;
  const [otlp, syslog, health, metrics, selfMetrics] = await Promise.all(Array.from({length: 5}, unusedPort));
  for (const name of ['archive', 'hot', 'restore', 'restored']) await mkdir(resolve(output, name));
  const proof = {
    extensions: {health_check: {endpoint: `127.0.0.1:${health}`},
      file_storage: {directory: resolve(output, 'hot')},
      'file_storage/archive': {directory: resolve(output, 'archive')}},
    receivers: {otlp: {protocols: {http: {endpoint: `127.0.0.1:${otlp}`}}},
      syslog: {tcp: {listen_address: `127.0.0.1:${syslog}`}},
      'host_metrics/capacity': {scrapers: {filesystem: {include_mount_points: {mount_points: ['/']}}}}},
    exporters: {'awss3/archive': {s3uploader: {endpoint: `http://127.0.0.1:${port}`,
      disable_ssl: true, s3_force_path_style: true}},
      'otlp_http/loki': {endpoint: `http://127.0.0.1:${port}/loki`},
      'otlp_http/tempo': {endpoint: `http://127.0.0.1:${port}/tempo`},
      prometheus: {endpoint: `127.0.0.1:${metrics}`}},
    service: {telemetry: {metrics: {readers: [{pull: {exporter: {prometheus: {host: '127.0.0.1', port: selfMetrics}}}}]}}},
  };
  const patch = resolve(output, 'proof.json');
  await writeFile(patch, JSON.stringify(proof));
  const args = [`--config=${resolve(root, 'deployment/observability/collector/collector.yaml')}`,
    `--config=${resolve(here, 'collector.yaml')}`, `--config=${patch}`];
  await native(['validate', ...args], 'native-config');
  collector = await launch(args, 'collector-before-kill');
  async function healthy() {
    try {return (await fetch(`http://127.0.0.1:${health}`, {signal: AbortSignal.timeout(500)})).ok;} catch {return false;}
  }
  await waitFor(healthy, 'native collector startup');
  async function send(index) {
    const traceId = String(index).repeat(32), spanId = String(index).repeat(16);
    const rid = `00000000-0000-0000-0000-${String(index).padStart(12, '0')}`;
    const timestamp = String(BigInt(Date.now()) * 1000000n);
    const payload = {resourceSpans: [{resource: {attributes: [
      {key: 'service.name', value: {stringValue: 'studymate-api'}},
      {key: 'private.resource', value: {stringValue: canary}}]},
      scopeSpans: [{scope: {name: 'synthetic'}, spans: [{traceId, spanId, name: 'GET /api/v1/me',
        kind: 2, startTimeUnixNano: timestamp, endTimeUnixNano: timestamp,
        attributes: [{key: 'request.id', value: {stringValue: rid}},
          {key: 'db.statement', value: {stringValue: canary}}],
        status: {message: canary}, events: [{name: canary, timeUnixNano: timestamp}]}]}]}]};
    const result = await fetch(`http://127.0.0.1:${otlp}/v1/traces`, {method: 'POST',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal: AbortSignal.timeout(3000)});
    assert(result.ok, 'Native OTLP trace rejected');
    const log = {time: '2026-11-11T00:00:00+00:00', level: 'INFO', event: 'request_completed',
      method: 'GET', route: '/api/v1/me', request_id: rid, status: 200, password: canary, message: canary};
    await new Promise((done, fail) => {
      const stream = createConnection({host: '127.0.0.1', port: syslog}, () => {
        stream.end(`<14>1 2026-11-11T00:00:00Z synthetic studymate-api 123 - - ${JSON.stringify(log)}\n`);
      });
      stream.once('error', fail); stream.once('close', done);
    });
  }
  await send(1);
  await waitFor(() => rejected >= 2, 'both sanitized signal uploads reach controlled outage');
  await stop(collector, 'SIGKILL');
  accepting = true;
  collector = await launch(args, 'collector-after-restart');
  await waitFor(healthy, 'native collector restart');
  await waitFor(() => objects.size >= 2, 'persistent queues recover after SIGKILL');
  await send(2);
  await waitFor(() => objects.size >= 4, 'second pair uses collision-resistant keys');
  await stop(collector);
  assert.equal(overwrites, 0);
  let logs = 0, traces = 0;
  const receipts = [];
  for (const [key, object] of objects) {
    const index = receipts.length;
    await writeFile(resolve(output, `object-${index}.json.gz`), object.body);
    await writeFile(resolve(output, 'restore', `object-${index}.json`), object.json + '\n');
    logs += object.parsed.resourceLogs ? 1 : 0;
    traces += object.parsed.resourceSpans ? 1 : 0;
    receipts.push({key, sha256: createHash('sha256').update(object.body).digest('hex')});
  }
  assert(logs >= 2 && traces >= 2);
  const restorePatch = resolve(output, 'restore-patch.json');
  await writeFile(restorePatch, JSON.stringify({receivers: {'otlp_json_file/archive': {
    include: [resolve(output, 'restore', '*.json')]}}, exporters: {'file/restored': {
      path: resolve(output, 'restored', 'restored.json')}}}));
  const restoreArgs = [`--config=${resolve(here, 'restore.yaml')}`, `--config=${restorePatch}`];
  await native(['validate', ...restoreArgs], 'restore-config');
  collector = await launch(restoreArgs, 'restore');
  const restored = resolve(output, 'restored', 'restored.json');
  await waitFor(async () => {
    try {const text = await readFile(restored, 'utf8'); return text.includes('resourceLogs') && text.includes('resourceSpans') && text.includes('request.id');} catch {return false;}
  }, 'native offline JSON restoration');
  await stop(collector);
  const text = await readFile(restored, 'utf8');
  assert(!text.includes(canary));
  const receipt = {status: 'PASS', image, objects: receipts, logs, traces, overwrites,
    controlled_outage_attempts: rejected, persistence: 'SIGKILL recovery', restore: 'native otlp_json_file → file',
    live_s3: false, real_credentials: false, kernel_read_only_proof: false};
  await writeFile(resolve(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({status: 'PASS', artifact: output, objects: objects.size}));
} catch (error) {
  console.error(JSON.stringify({status: 'FAIL', artifact: output, error: error.message}));
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  await stop(collector, 'SIGKILL');
  if (extracted) docker(['rm', extracted]);
  sink.closeAllConnections();
  await new Promise(done => sink.close(done));
}
