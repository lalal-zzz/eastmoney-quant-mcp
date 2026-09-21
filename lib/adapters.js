import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { userHome } from "./paths.js"

// skills/ 目录名即 skill id (GitHub skills 仓库惯例: skills/<skill-id>/SKILL.md)。
// 目录列表即安装清单 —— 新增/删除 skill 不需要改任何映射表。
function listSkillIds(packageRoot) {
  const source = join(packageRoot, "skills")
  if (!existsSync(source)) return []
  return readdirSync(source, { withFileTypes: true })
    .filter((d) => d.isDirectory() && existsSync(join(source, d.name, "SKILL.md")))
    .map((d) => d.name)
}

function readJson(path) { return existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {} }
function writeJson(path, data) { mkdirSync(dirname(path), { recursive: true }); writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`) }
function copySkills(packageRoot, root) {
  const source = join(packageRoot, "skills")
  const ids = listSkillIds(packageRoot)
  for (const name of ids) {
    const target = join(root, name)
    mkdirSync(target, { recursive: true })
    cpSync(join(source, name, "SKILL.md"), join(target, "SKILL.md"))
  }
  return ids.map((name) => join(root, name, "SKILL.md"))
}

function removeSkills(packageRoot, root) {
  const removed = []
  for (const name of listSkillIds(packageRoot)) {
    const target = join(root, name)
    if (existsSync(target)) {
      rmSync(target, { recursive: true, force: true })
      removed.push(target)
    }
  }
  return removed
}

// VS Code user config dir (Copilot MCP). STOCK_ANALYSIS_HOME keeps test writes hermetic.
function vscodeUserDir() {
  if (process.env.STOCK_ANALYSIS_HOME) return join(userHome(), "Code", "User")
  if (process.platform === "win32") return join(process.env.APPDATA || join(userHome(), "AppData", "Roaming"), "Code", "User")
  if (process.platform === "darwin") return join(userHome(), "Library", "Application Support", "Code", "User")
  return join(userHome(), ".config", "Code", "User")
}

// Factory for JSON-config agents ({mcpServers: {...}} style, or VS Code {servers: {...}}).
// skillRoot is optional: Cursor/Copilot do not consume SKILL.md, so only the MCP server is registered.
function jsonAdapter({ id, configPath, serversKey = "mcpServers", skillRoot = null, detect, entry = (command) => command }) {
  let _packageRoot = null
  return {
    id,
    configPath,
    skillRoot,
    detect,
    install(packageRoot, command) {
      _packageRoot = packageRoot
      const path = this.configPath(); const config = readJson(path)
      config[serversKey] ??= {}
      const next = entry(command)
      const changed = JSON.stringify(config[serversKey]["stock-analysis"]) !== JSON.stringify(next)
      config[serversKey]["stock-analysis"] = next
      writeJson(path, config)
      return { configPath: path, changed, skills: this.skillRoot ? copySkills(packageRoot, this.skillRoot()) : [] }
    },
    uninstall(removeConfig = true) {
      const path = this.configPath()
      if (removeConfig && existsSync(path)) {
        const config = readJson(path)
        if (config[serversKey]) delete config[serversKey]["stock-analysis"]
        writeJson(path, config)
      }
      return { configPath: path, skills: this.skillRoot && _packageRoot ? removeSkills(_packageRoot, this.skillRoot()) : [] }
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
    _packageRoot: null,
    configPath: () => join(userHome(), ".codex", "config.toml"),
    skillRoot: () => join(userHome(), ".codex", "skills"),
    detect() { return existsSync(this.configPath()) || existsSync(join(userHome(), ".codex")) },
    install(packageRoot, command) {
      this._packageRoot = packageRoot
      const path = this.configPath(); mkdirSync(dirname(path), { recursive: true })
      let content = existsSync(path) ? readFileSync(path, "utf8") : ""
      const section = `[mcp_servers.stock-analysis]\ncommand = "${command.command}"\nargs = [${command.args.map((x) => JSON.stringify(x)).join(", ")}]\n`
      const pattern = /^\[mcp_servers\.stock-analysis\]\n(?:(?!\[)[^\n]*\n?)*/m
      const changed = !pattern.test(content) || !pattern.exec(content)[0].includes(section.trim())
      content = pattern.test(content) ? content.replace(pattern, section) : `${content.trimEnd()}${content.trim() ? "\n\n" : ""}${section}`
      writeFileSync(path, content)
      return { configPath: path, changed, skills: copySkills(packageRoot, this.skillRoot()) }
    },
    uninstall(removeConfig = true) {
      const path = this.configPath()
      if (removeConfig && existsSync(path)) {
        const content = readFileSync(path, "utf8").replace(/^\[mcp_servers\.stock-analysis\]\n(?:(?!\[)[^\n]*\n?)*/m, "").trimEnd()
        writeFileSync(path, content ? `${content}\n` : "")
      }
      return { configPath: path, skills: this._packageRoot ? removeSkills(this._packageRoot, this.skillRoot()) : [] }
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
  const mcpServers = JSON.stringify({ mcpServers: { "stock-analysis": command } }, null, 2)
  return { opencode: mcpServers, "generic-mcp-client": mcpServers }
}
