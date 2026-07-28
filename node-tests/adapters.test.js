import test from "node:test"
import assert from "node:assert/strict"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"

const home = mkdtempSync(join(tmpdir(), "eastmoney-quant-test-"))
process.env.EASTMONEY_QUANT_HOME = home
const { ADAPTERS } = await import("../lib/adapters.js")
const { install } = await import("../lib/installer.js")

test.after(() => rmSync(home, { recursive: true, force: true }))

test("dry run never writes files", async () => {
  const result = await install({ packageRoot: join(process.cwd()), agents: "codex", dryRun: true })
  assert.equal(result.dryRun, true)
  assert.equal(existsSync(join(home, ".codex", "config.toml")), false)
})

test("Codex adapter preserves unrelated configuration and is idempotent", () => {
  const adapter = ADAPTERS.codex
  const path = adapter.configPath()
  mkdirSync(join(home, ".codex"), { recursive: true })
  writeFileSync(path, '[model]\nname = "example"\n')
  const command = { command: "node", args: ["server.js"] }
  adapter.install(process.cwd(), command)
  adapter.install(process.cwd(), command)
  const content = readFileSync(path, "utf8")
  assert.match(content, /\[model\]/)
  assert.equal((content.match(/\[mcp_servers\.eastmoney-quant\]/g) || []).length, 1)
})

test("Cursor adapter preserves other servers, registers no skills", () => {
  const adapter = ADAPTERS.cursor
  const path = adapter.configPath()
  mkdirSync(join(home, ".cursor"), { recursive: true })
  writeFileSync(path, JSON.stringify({ mcpServers: { other: { command: "x", args: [] } } }))
  const command = { command: "node", args: ["server.js"] }
  const first = adapter.install(process.cwd(), command)
  const second = adapter.install(process.cwd(), command)
  assert.equal(first.changed, true)
  assert.equal(second.changed, false)
  assert.equal(first.skills.length, 0)
  const config = JSON.parse(readFileSync(path, "utf8"))
  assert.deepEqual(config.mcpServers["eastmoney-quant"], command)
  assert.ok(config.mcpServers.other)
  adapter.uninstall()
  assert.equal("eastmoney-quant" in JSON.parse(readFileSync(path, "utf8")).mcpServers, false)
})

test("Copilot adapter writes VS Code servers format with stdio type", () => {
  const adapter = ADAPTERS.copilot
  const command = { command: "node", args: ["server.js"] }
  adapter.install(process.cwd(), command)
  const config = JSON.parse(readFileSync(adapter.configPath(), "utf8"))
  assert.deepEqual(config.servers["eastmoney-quant"], { type: "stdio", ...command })
})

test("Qoder adapter installs mcp server and skills", () => {
  const adapter = ADAPTERS.qoder
  mkdirSync(join(home, ".qoder"), { recursive: true })
  assert.equal(adapter.detect(), true)
  const command = { command: "node", args: ["server.js"] }
  const result = adapter.install(process.cwd(), command)
  assert.equal(result.skills.length, 4)
  assert.ok(existsSync(join(home, ".qoder", "skills", "eastmoney-quant", "SKILL.md")))
  const config = JSON.parse(readFileSync(adapter.configPath(), "utf8"))
  assert.deepEqual(config.mcpServers["eastmoney-quant"], command)
  adapter.uninstall()
  assert.equal(existsSync(join(home, ".qoder", "skills", "eastmoney-quant")), false)
})
