#!/usr/bin/env node

/**
 * stock-analysis-mcp — Node.js shim
 *
 * Invokes the Python MCP server via stdio.
 * Allows `npx stock-analysis-mcp` to work as an MCP server.
 */

import { spawn } from "node:child_process"
import { delimiter, dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { resolveRuntimePython } from "./lib/installer.js"

const __dirname = dirname(fileURLToPath(import.meta.url))

const PYTHON = resolveRuntimePython()
const SERVER_MODULE = "stock_analysis_mcp.server"

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

proc.on("error", (err) => {
  console.error(`[stock-analysis-mcp] failed to start Python (${PYTHON}): ${err.message}`)
  console.error("[stock-analysis-mcp] run `stock-analysis doctor` or set STOCK_ANALYSIS_PYTHON to a valid interpreter.")
  process.exit(1)
})

proc.on("exit", (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0))
})

// 转发原始信号, 让 Python 侧能优雅收尾 (SIGTERM/SIGINT 由信号名对应转发)
for (const sig of ["SIGTERM", "SIGINT"]) {
  process.on(sig, () => proc.kill(sig))
}

function cleanup() {
  try { proc.kill() } catch (_) { /* ignore */ }
}
process.on("exit", cleanup)
process.on("uncaughtException", (err) => {
  console.error("[stock-analysis-mcp] fatal:", err.message)
  cleanup()
  process.exit(1)
})
