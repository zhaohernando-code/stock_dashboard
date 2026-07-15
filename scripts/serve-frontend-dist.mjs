#!/usr/bin/env node

import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";

function argValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index + 1 >= process.argv.length) return fallback;
  return process.argv[index + 1];
}

const root = path.resolve(argValue("--root", path.join(process.cwd(), "dist")));
const host = argValue("--host", "127.0.0.1");
const port = Number(argValue("--port", "5174"));
const mimeTypes = new Map([
  [".css", "text/css; charset=utf-8"],
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".map", "application/json; charset=utf-8"],
  [".png", "image/png"],
  [".svg", "image/svg+xml"],
  [".webp", "image/webp"],
]);

function isInsideRoot(filePath) {
  const relative = path.relative(root, filePath);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

async function resolveFile(requestPath) {
  const decoded = decodeURIComponent(requestPath.split("?")[0] || "/");
  const normalized = decoded.replace(/^\/+/, "");
  let filePath = path.resolve(root, normalized);
  if (!isInsideRoot(filePath)) return { status: 403 };

  try {
    const fileStat = await stat(filePath);
    if (fileStat.isDirectory()) filePath = path.join(filePath, "index.html");
    await stat(filePath);
    return { filePath };
  } catch {
    if (path.extname(filePath)) return { status: 404 };
    return { filePath: path.join(root, "index.html") };
  }
}

const server = createServer(async (request, response) => {
  try {
    const resolved = await resolveFile(request.url ?? "/");
    if (resolved.status) {
      response.writeHead(resolved.status);
      response.end();
      return;
    }
    const filePath = resolved.filePath;
    const body = await readFile(filePath);
    const contentType = mimeTypes.get(path.extname(filePath)) ?? "application/octet-stream";
    const acceptsGzip = /(?:^|,)\s*gzip\s*(?:,|$)/i.test(String(request.headers["accept-encoding"] ?? ""));
    const compressible = /^(?:text\/|application\/(?:javascript|json))/.test(contentType);
    const servedBody = acceptsGzip && compressible && body.length >= 1024 ? gzipSync(body) : body;
    const headers = {
      "Cache-Control": path.basename(filePath) === "index.html" ? "no-cache" : "public, max-age=31536000, immutable",
      "Content-Length": String(servedBody.length),
      "Content-Type": contentType,
      "Vary": "Accept-Encoding",
    };
    if (servedBody !== body) headers["Content-Encoding"] = "gzip";
    response.writeHead(200, {
      ...headers,
    });
    response.end(request.method === "HEAD" ? undefined : servedBody);
  } catch (error) {
    console.error(error);
    response.writeHead(500);
    response.end();
  }
});

server.listen(port, host, () => {
  console.log(`frontend dist server listening at http://${host}:${port}/`);
});
