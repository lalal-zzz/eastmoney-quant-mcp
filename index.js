#!/usr/bin/env node

/**
 * eastmoney-quant-mcp — Node.js shim
 *
 * Invokes the Python MCP server via stdio.
 * Allows `npx eastmoney-quant-mcp` to work as an MCP server.
 */

import { spawn } from "node:child_process"
import { delimiter, dirname, join } from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = dirname(fileURLToPath(import.meta.url))

const PYTHON = process.env.EASTMONEY_PYTHON || "python"
const SERVER_MODULE = "eastmoney_quant_mcp.server"

const pySrc = join(__dirname, "src")
// 使用平台对应的路径分隔符(Windows 为 ";", POSIX 为 ":")
const env = {
  ...process.env,
  PYTHONPATH: process.env.PYTHONPATH ? `${pySrc}${delimiter}${process.env.PYTHONPATH}` : pySrc,
}

const proc = spawn(PYTHON, ["-m", SERVER_MODULE], {
  env,
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
})

process.stdin.pipe(proc.stdin)
proc.stdout.pipe(process.stdout)
proc.stderr.pipe(process.stderr)

proc.on("exit", (code) => {
  process.exit(code ?? 1)
})

process.on("SIGTERM", () => proc.kill())
process.on("SIGINT", () => proc.kill())

function cleanup() {
  try { proc.kill() } catch (_) { /* ignore */ }
}
process.on("exit", cleanup)
process.on("uncaughtException", (err) => {
  console.error("[eastmoney-quant-mcp] fatal:", err.message)
  cleanup()
  process.exit(1)
})
