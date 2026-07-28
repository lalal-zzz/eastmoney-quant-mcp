import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { userHome } from "./paths.js"

const skillNames = ["eastmoney-quant", "eastmoney-quant-data-init", "eastmoney-quant-stock-screening", "eastmoney-quant-report-generation"]

function readJson(path) { return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {} }
function writeJson(path, data) { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`) }
function copySkills(packageRoot, root) {
  const source = join(packageRoot, "src", "eastmoney_quant_mcp", "skill")
  const mapping = {
    "eastmoney-quant": "SKILL.md",
    "eastmoney-quant-data-init": join("data-init", "SKILL.md"),
    "eastmoney-quant-stock-screening": join("stock-screening", "SKILL.md"),
    "eastmoney-quant-report-generation": join("report-generation", "SKILL.md"),
  }
  for (const name of skillNames) {
    const target = join(root, name)
    mkdirSync(target, { recursive: true })
    cpSync(join(source, mapping[name]), join(target, "SKILL.md"))
  }
  return skillNames.map((name) => join(root, name, "SKILL.md"))
}

function removeSkills(root) {
  const removed = []
  for (const name of skillNames) {
    const target = join(root, name)
    if (existsSync(target)) {
      rmSync(target, { recursive: true, force: true })
      removed.push(target)
    }
  }
  return removed
}

// VS Code user config dir (Copilot MCP). EASTMONEY_QUANT_HOME keeps test writes hermetic.
function vscodeUserDir() {
  if (process.env.EASTMONEY_QUANT_HOME) return join(userHome(), "Code", "User")
  if (process.platform === "win32") return join(process.env.APPDATA || join(userHome(), "AppData", "Roaming"), "Code", "User")
  if (process.platform === "darwin") return join(userHome(), "Library", "Application Support", "Code", "User")
  return join(userHome(), ".config", "Code", "User")
}

// Factory for JSON-config agents ({mcpServers: {...}} style, or VS Code {servers: {...}}).
// skillRoot is optional: Cursor/Copilot do not consume SKILL.md, so only the MCP server is registered.
function jsonAdapter({ id, configPath, serversKey = "mcpServers", skillRoot = null, detect, entry = (command) => command }) {
  return {
    id,
    configPath,
    skillRoot,
    detect,
    install(packageRoot, command) {
      const path = this.configPath(); const config = readJson(path)
      config[serversKey] ??= {}
      const next = entry(command)
      const changed = JSON.stringify(config[serversKey]["eastmoney-quant"]) !== JSON.stringify(next)
      config[serversKey]["eastmoney-quant"] = next
      writeJson(path, config)
      return { configPath: path, changed, skills: this.skillRoot ? copySkills(packageRoot, this.skillRoot()) : [] }
    },
    uninstall(removeConfig = true) {
      const path = this.configPath()
      if (removeConfig && existsSync(path)) {
        const config = readJson(path)
        if (config[serversKey]) delete config[serversKey]["eastmoney-quant"]
        writeJson(path, config)
      }
      return { configPath: path, skills: this.skillRoot ? removeSkills(this.skillRoot()) : [] }
    },
  }
}

export const ADAPTERS = {
  "claude-code": jsonAdapter({
    id: "claude-code",
    configPath: () => join(userHome(), ".claude.json"),
    skillRoot: () => join(userHome(), ".claude", "skills"),
    detect: () => existsSync(join(userHome(), ".claude.json")) || existsSync(join(userHome(), ".claude")),
  }),
  codex: {
    id: "codex",
    configPath: () => join(userHome(), ".codex", "config.toml"),
    skillRoot: () => join(userHome(), ".codex", "skills"),
    detect() { return existsSync(this.configPath()) || existsSync(join(userHome(), ".codex")) },
    install(packageRoot, command) {
      const path = this.configPath(); mkdirSync(dirname(path), { recursive: true })
      let content = existsSync(path) ? readFileSync(path, "utf8") : ""
      const section = `[mcp_servers.eastmoney-quant]\ncommand = "${command.command}"\nargs = [${command.args.map((x) => JSON.stringify(x)).join(", ")}]\n`
      const pattern = /^\[mcp_servers\.eastmoney-quant\][\s\S]*?(?=^\[|$)/m
      const changed = !pattern.test(content) || !pattern.exec(content)[0].includes(section.trim())
      content = pattern.test(content) ? content.replace(pattern, section) : `${content.trimEnd()}${content.trim() ? "\n\n" : ""}${section}`
      writeFileSync(path, content)
      return { configPath: path, changed, skills: copySkills(packageRoot, this.skillRoot()) }
    },
    uninstall(removeConfig = true) {
      const path = this.configPath()
      if (removeConfig && existsSync(path)) {
        const content = readFileSync(path, "utf8").replace(/^\[mcp_servers\.eastmoney-quant\][\s\S]*?(?=^\[|$)/m, "").trimEnd()
        writeFileSync(path, content ? `${content}\n` : "")
      }
      return { configPath: path, skills: removeSkills(this.skillRoot()) }
    },
  },
  cursor: jsonAdapter({
    id: "cursor",
    configPath: () => join(userHome(), ".cursor", "mcp.json"),
    detect: () => existsSync(join(userHome(), ".cursor")),
  }),
  copilot: jsonAdapter({
    id: "copilot",
    configPath: () => join(vscodeUserDir(), "mcp.json"),
    serversKey: "servers",
    detect: () => existsSync(vscodeUserDir()),
    entry: (command) => ({ type: "stdio", ...command }),
  }),
  qoder: jsonAdapter({
    id: "qoder",
    configPath: () => join(userHome(), ".qoder", "mcp.json"),
    skillRoot: () => join(userHome(), ".qoder", "skills"),
    detect: () => existsSync(join(userHome(), ".qoder")),
  }),
}

export function manualTemplates(command) {
  const mcpServers = JSON.stringify({ mcpServers: { "eastmoney-quant": command } }, null, 2)
  return { opencode: mcpServers, "generic-mcp-client": mcpServers }
}
