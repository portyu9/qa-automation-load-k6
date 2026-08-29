'use strict';

const http = require('node:http');

const host = '127.0.0.1';
const port = Number(process.env.LOCAL_API_PORT || 4020);

if (!Number.isInteger(port) || port < 1 || port > 65_535) {
  throw new Error('LOCAL_API_PORT must be an integer between 1 and 65535');
}

const post = Object.freeze({
  userId: 1,
  id: 1,
  title: 'deterministic-local-post',
  body: 'repository-owned k6 smoke fixture',
});

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${host}:${port}`);

  if (req.method === 'GET' && url.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify({ status: 'ok' }));
    return;
  }

  if (req.method === 'GET' && url.pathname === '/posts/1') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(post));
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify({ error: 'not_found' }));
});

server.listen(port, host, () => {
  console.log(`k6 local API listening on http://${host}:${port}`);
});

function shutdown(signal) {
  console.log(`received ${signal}; closing k6 local API`);
  server.close((error) => {
    if (error) {
      console.error(error);
      process.exitCode = 1;
    }
  });
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
