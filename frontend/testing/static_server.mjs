import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, resolve, sep } from 'node:path';

// Test only: serve actual build artifacts, with the documented CSR fallback.
const root = resolve('dist/studymate/browser');
const types = Object.freeze({
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
  '.png': 'image/png',
  '.txt': 'text/plain; charset=utf-8',
});
createServer(async (request, response) => {
  if (request.method !== 'GET') {
    response.writeHead(405).end();
    return;
  }
  try {
    const path = decodeURIComponent(new URL(request.url ?? '/', 'http://127.0.0.1').pathname);
    const target = resolve(root, `.${path === '/' ? '/index.html' : path}`);
    if (!target.startsWith(`${root}${sep}`)) {
      response.writeHead(404).end();
      return;
    }
    const file = extname(target) === '' ? resolve(root, 'index.csr.html') : target;
    const content = await readFile(file);
    response
      .writeHead(200, {
        'Content-Type': types[extname(file)] ?? 'application/octet-stream',
        'Cache-Control': 'no-store',
      })
      .end(content);
  } catch {
    response.writeHead(404).end();
  }
}).listen(Number(process.env['STUDYMATE_TEST_PORT'] ?? '4317'), '127.0.0.1');
