// One bounded native proof. No Python/backend edits, real credentials or cloud calls.
import assert from 'node:assert/strict';
import {spawn, spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {createServer, request as httpRequest} from 'node:http';
import {createConnection, createServer as tcpServer} from 'node:net';
import {mkdtemp, mkdir, readFile, writeFile, readdir, cp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {dirname, resolve, relative} from 'node:path';
import {fileURLToPath} from 'node:url';
import {gunzipSync} from 'node:zlib';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../../..');
const image = 'otel/opentelemetry-collector-contrib:0.165.0@sha256:e40d61f10c9a617cca1ffd1be4d7e2b3a4b0f0001798ff07e58cabe82e618cea';
const output = await mkdtemp(resolve(tmpdir(), 'peerly-archive-crypt-'));
const rcloneImage = 'rclone/rclone:1.76.0@sha256:7cbeec24a44f206067597c0368be4de90ae19a64d5113c7d1938bd737a81e466';
let gateway, rawServer, gatewayPort, gatewayArgs, rcloneEnv;
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
  AWS_ACCESS_KEY_ID: 'gateway', AWS_SECRET_ACCESS_KEY: 'synthetic-gateway-secret',
  AWS_SHARED_CREDENTIALS_FILE: '/dev/null', AWS_CONFIG_FILE: '/dev/null',
  AWS_EC2_METADATA_DISABLED: 'true',
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
      const forwarding = Object.fromEntries(Object.entries(request.headers).filter(([key]) =>
        !['connection','transfer-encoding'].includes(key)));
      const uploaded = await new Promise((done, fail) => {
        const forwarded=httpRequest({hostname:'127.0.0.1',port:gatewayPort,path:request.url,
          method:'PUT',headers:forwarding,timeout:10000},reply=>{
          const parts=[];let size=0;
          reply.on('data',part=>{size+=part.length;if(size>4096){forwarded.destroy();fail(new Error('S3 response bound'));}else parts.push(part);});
          reply.on('end',()=>done({status:reply.statusCode,body:Buffer.concat(parts).toString()}));
        });
        forwarded.once('error',fail);forwarded.once('timeout',()=>forwarded.destroy(new Error('S3 fixture timeout')));
        forwarded.end(Buffer.concat(chunks));
      });
      const rejection=uploaded.body.match(/<Code>([A-Za-z0-9]+)<\/Code>/)?.[1] ?? 'unknown';
      assert.equal(uploaded.status,200,'Native gateway rejected: '+rejection);
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
      assert(request.url.startsWith('/ingest/peerly/test/'), 'Resource-controlled routing escaped');
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
function launchRclone(args, name, environment) {
  const child=spawn(resolve(output,'rclone'),args,{env:environment});
  const chunks=[];
  child.stderr.on('data',part=>chunks.push(part));
  child.stdout.on('data',part=>chunks.push(part));
  child.once('error',error=>{fixtureError=error;});
  child.once('exit',()=>{void writeFile(resolve(output,name+'.log'),Buffer.concat(chunks));});
  return child;
}
async function stop(child, signal = 'SIGTERM') {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const ended = new Promise(done => child.once('exit', done));
  child.kill(signal);
  await ended;
}
try {
  deadline = setTimeout(() => {fixtureError = new Error('Proof exceeded150s'); collector?.kill('SIGKILL');}, 150000);
  // Extract the locally present immutable image's binary; do not pull or run a host-privileged container.
  docker(['image', 'inspect', image]);
  extracted = docker(['create', '--network=none', image]);
  docker(['cp', `${extracted}:/otelcol-contrib`, resolve(output, 'otelcol-contrib')]);
  docker(['rm', extracted]);
  extracted = undefined;
  docker(['image', 'inspect', rcloneImage]);
  extracted = docker(['create', '--network=none', rcloneImage]);
  docker(['cp', extracted + ':/usr/local/bin/rclone', resolve(output, 'rclone')]);
  docker(['rm', extracted]); extracted = undefined;
  const rclone = resolve(output, 'rclone');
  rcloneEnv = {...cleanEnv, RCLONE_AUTH_KEY: '"gateway,synthetic-gateway-secret"', GOMEMLIMIT: '160MiB'};
  const password = spawnSync(rclone, ['obscure','synthetic-native-crypt-password'], {env: cleanEnv, encoding:'utf8'}).stdout.trim();
  const salt = spawnSync(rclone, ['obscure','synthetic-distinct-native-crypt-salt'], {env: cleanEnv, encoding:'utf8'}).stdout.trim();
  const wrongPassword = spawnSync(rclone, ['obscure','different-synthetic-password'], {env: cleanEnv, encoding:'utf8'}).stdout.trim();
  assert(password && salt && wrongPassword);
  const rawPort = await unusedPort(); gatewayPort = await unusedPort();
  const store = resolve(output, 'raw-store');
  await mkdir(resolve(store, 'peerly-archive'), {recursive:true});
  const caps = ['--vfs-cache-mode=off','--buffer-size=0','--streaming-upload-cutoff=1Mi',
    '--s3-chunk-size=5Mi','--s3-upload-concurrency=1','--max-buffer-memory=32Mi',
    '--multipart-max-uploads=2','--multipart-streaming-buffer-limit=5Mi',
    '--multipart-streaming-buffer-total=10Mi','--metadata-max-objects=128',
    '--server-read-timeout=15s','--server-write-timeout=15s','--contimeout=5s','--timeout=5s',
    '--retries=1','--low-level-retries=1','--stats=0','--log-level=ERROR'];
  const rawConfig = resolve(output, 'raw.conf');
  await writeFile(rawConfig, '[local]\ntype = local\n', {mode:0o600});
  rawServer = launchRclone(['serve','s3','local:' + store,'--config=' + rawConfig,
    '--addr=127.0.0.1:' + rawPort, ...caps], 'raw-server', {...rcloneEnv,RCLONE_AUTH_KEY:'"raw,synthetic-raw-secret"'});
  await waitFor(async()=> {try {return (await fetch('http://127.0.0.1:'+rawPort)).status===403;}catch{return false;}},'native raw S3 startup');
  const config = resolve(output, 'gateway.conf');
  const configuration = '[raw]\ntype = s3\nprovider = Rclone\nendpoint = http://127.0.0.1:' + rawPort +
    '\nregion = us-east-1\naccess_key_id = raw\nsecret_access_key = synthetic-raw-secret\nforce_path_style = true\nno_check_bucket = true\n' +
    '[encrypted]\ntype = crypt\nremote = raw:peerly-archive/crypt-v1\nfilename_encryption = standard\ndirectory_name_encryption = true\npassword = ' + password + '\npassword2 = '+salt+'\n';
  await writeFile(config, configuration, {mode:0o600});
  // Native encrypted marker makes the virtual bucket persistent; no Cloud bucket creation.
  const seeded=spawnSync(rclone,['rcat','encrypted:ingest/.gateway-format','--config='+config,
    '--retries=1','--low-level-retries=1'],{env:cleanEnv,input:'peerly archive crypt-v1',encoding:'utf8',timeout:15000});
  await writeFile(resolve(output,'seed.log'),seeded.stderr); assert.equal(seeded.status,0,'Native marker bootstrap failed');
  gatewayArgs=['serve','s3','encrypted:','--config='+config,'--addr=127.0.0.1:'+gatewayPort,...caps];
  gateway=launchRclone(gatewayArgs,'gateway-first',rcloneEnv);
  async function gatewayUp(){try{return (await fetch('http://127.0.0.1:'+gatewayPort)).status===403;}catch{return false;}}
  await waitFor(gatewayUp,'native crypt gateway denies unsigned access');
  const badConfig=resolve(output,'bad-auth.conf');
  await writeFile(badConfig,'[bad]\ntype = s3\nprovider = Rclone\nendpoint = http://127.0.0.1:'+gatewayPort+
    '\naccess_key_id = gateway\nsecret_access_key = wrong-gateway-secret\nforce_path_style = true\n', {mode:0o600});
  const denied=spawnSync(rclone,['lsf','bad:ingest','--config='+badConfig,'--retries=1','--low-level-retries=1'],
    {env:cleanEnv,encoding:'utf8',timeout:15000}); assert.notEqual(denied.status,0,'Wrong signature accepted');
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
      disable_ssl: true, s3_force_path_style: true, s3_bucket: 'ingest'}},
      'otlp_http/loki': {endpoint: `http://127.0.0.1:${port}/loki`},
      'otlp_http/tempo': {endpoint: `http://127.0.0.1:${port}/tempo`},
      prometheus: {endpoint: `127.0.0.1:${metrics}`}},
    service: {telemetry: {metrics: {readers: [{pull: {exporter: {prometheus: {host: '127.0.0.1', port: selfMetrics}}}}]}}},
  };
  const patch = resolve(output, 'proof.json');
  await writeFile(patch, JSON.stringify(proof));
  const args = [`--config=${resolve(root, 'deployment/observability/collector/collector.yaml')}`,
    `--config=${resolve(here, '../collector.yaml')}`, `--config=${resolve(here, 'collector.yaml')}`, `--config=${patch}`];
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
  await stop(gateway);
  gateway=launchRclone(gatewayArgs,'gateway-restarted',rcloneEnv);
  await waitFor(async()=> {try{return (await fetch('http://127.0.0.1:'+gatewayPort)).status===403;}catch{return false;}},'gateway restart with persistent virtual bucket');
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
  await stop(gateway); await stop(rawServer);
  async function files(directory) {
    const result=[];
    for(const entry of await readdir(directory,{withFileTypes:true})) {
      const path=resolve(directory,entry.name);
      result.push(...(entry.isDirectory()?await files(path):[path]));
    } return result;
  }
  const cipherRoot=resolve(store,'peerly-archive','crypt-v1');
  const ciphertexts=await files(cipherRoot); assert(ciphertexts.length>=5);
  for(const path of ciphertexts){const bytes=await readFile(path); assert(bytes.subarray(0,8).equals(Buffer.from('RCLONE\0\0')));
    assert(!bytes.includes(Buffer.from(canary))); assert(!bytes.subarray(0,2).equals(Buffer.from([31,139])));}
  function localConfig(path, key=password) {return '[offline]\ntype = crypt\nremote = '+path+
    '\nfilename_encryption = standard\ndirectory_name_encryption = true\npassword = '+key+'\npassword2 = '+salt+'\n';}
  const offline=resolve(output,'offline.conf'); await writeFile(offline,localConfig(cipherRoot),{mode:0o600});
  const decrypted=resolve(output,'offline-decrypted'); await mkdir(decrypted);
  const recovered=spawnSync(resolve(output,'rclone'),['copy','offline:ingest',decrypted,'--config='+offline,
    '--include=*.json.gz','--retries=1','--low-level-retries=1'],{env:cleanEnv,encoding:'utf8',timeout:15000});
  assert.equal(recovered.status,0,'Native offline decryption failed');
  const recoveredFiles=await files(decrypted); assert.equal(recoveredFiles.length,4);
  const expectedHashes=new Set(receipts.map(item=>item.sha256));
  for(let i=0;i<recoveredFiles.length;i++){const bytes=await readFile(recoveredFiles[i]);
    assert(expectedHashes.has(createHash('sha256').update(bytes).digest('hex')));
    await writeFile(resolve(output,'restore','object-'+i+'.json'),gunzipSync(bytes).toString()+'\n');}
  const wrong=resolve(output,'wrong-key.conf');await writeFile(wrong,localConfig(cipherRoot,wrongPassword),{mode:0o600});
  const failed=spawnSync(resolve(output,'rclone'),['cat','offline:ingest/'+relative(decrypted,recoveredFiles[0]),'--config='+wrong,
    '--retries=1','--low-level-retries=1'],{env:cleanEnv,encoding:'utf8',timeout:15000});
  assert.notEqual(failed.status,0); assert.equal(failed.stdout.length,0);
  const tamperedRoot=resolve(output,'tampered-cipher');await cp(cipherRoot,tamperedRoot,{recursive:true});
  for(const path of await files(tamperedRoot)){const bytes=await readFile(path);bytes[bytes.length-1]^=1;await writeFile(path,bytes);}
  const tampered=resolve(output,'tampered.conf'); await writeFile(tampered,localConfig(tamperedRoot),{mode:0o600});
  const rejectedTamper=spawnSync(resolve(output,'rclone'),['cat','offline:ingest/'+relative(decrypted,recoveredFiles[0]),'--config='+tampered,
    '--retries=1','--low-level-retries=1'],{env:cleanEnv,encoding:'utf8',timeout:15000});
  assert.notEqual(rejectedTamper.status,0); assert.equal(rejectedTamper.stdout.length,0);
  const restorePatch = resolve(output, 'restore-patch.json');
  await writeFile(restorePatch, JSON.stringify({receivers: {'otlp_json_file/archive': {
    include: [resolve(output, 'restore', '*.json')]}}, exporters: {'file/restored': {
      path: resolve(output, 'restored', 'restored.json')}}}));
  const restoreArgs = [`--config=${resolve(here, '../restore.yaml')}`, `--config=${restorePatch}`];
  await native(['validate', ...restoreArgs], 'restore-config');
  collector = await launch(restoreArgs, 'restore');
  const restored = resolve(output, 'restored', 'restored.json');
  await waitFor(async () => {
    try {
      const text = await readFile(restored, 'utf8');
      const data=text.trim().split('\n').map(line=>JSON.parse(line));
      let logs=0,spans=0;
      for(const item of data){
        for(const resource of item.resourceLogs??[])for(const scope of resource.scopeLogs??[])logs+=(scope.logRecords??[]).length;
        for(const resource of item.resourceSpans??[])for(const scope of resource.scopeSpans??[])spans+=(scope.spans??[]).length;
      }
      return logs===2 && spans===2 && [1,2].every(index=>text.includes(String(index).repeat(32)) &&
        text.includes('00000000-0000-0000-0000-'+String(index).padStart(12,'0')));
    } catch {return false;}
  }, 'native offline JSON restoration');
  await stop(collector);
  const text = await readFile(restored, 'utf8');
  assert(!text.includes(canary));
  const receipt = {status: 'PASS', image, objects: receipts, logs, traces, overwrites,
    controlled_outage_attempts: rejected, persistence: 'SIGKILL recovery', restore: 'native otlp_json_file → file',
    live_s3: false, real_credentials: false, kernel_read_only_proof: false, rclone_image: rcloneImage,
    encrypted_objects: ciphertexts.length, wrong_key_rejected: true, tamper_rejected: true, unsigned_and_wrong_signature_rejected: true, native_offline_decryption: true, gateway_restart: true, default_aws_checksum_interop: true, restored_log_records: 2, restored_spans: 2};
  await writeFile(resolve(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n');
  console.log(JSON.stringify({status: 'PASS', artifact: output, objects: objects.size}));
} catch (error) {
  console.error(JSON.stringify({status: 'FAIL', artifact: output, error: error.message}));
  process.exitCode = 1;
} finally {
  clearTimeout(deadline);
  await stop(collector, 'SIGKILL');
  await stop(gateway, 'SIGKILL'); await stop(rawServer, 'SIGKILL');
  if (extracted) docker(['rm', extracted]);
  sink.closeAllConnections();
  await new Promise(done => sink.close(done));
}
