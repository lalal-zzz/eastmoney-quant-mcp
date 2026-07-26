import { mkdirSync, copyFileSync, existsSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { homedir, platform } from "node:os"

const __dirname = dirname(fileURLToPath(import.meta.url))
const skillSrc = join(__dirname, "src", "eastmoney_quant_mcp", "skill", "SKILL.md")

if (!existsSync(skillSrc)) {
  console.log("[eastmoney-quant] SKILL.md not found, skipping skill install")
  process.exit(0)
}

const home = homedir()
const targets = [
  join(home, ".claude", "skills", "eastmoney-quant"),
  join(home, ".agents", "skills", "eastmoney-quant"),
]

for (const dir of targets) {
  try {
    mkdirSync(dir, { recursive: true })
    copyFileSync(skillSrc, join(dir, "SKILL.md"))
    console.log(`[eastmoney-quant] Skill installed → ${dir}`)
  } catch {
    // silently skip unavailable targets
  }
}
