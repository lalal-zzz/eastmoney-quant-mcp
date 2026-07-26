import { mkdirSync, copyFileSync, existsSync } from "node:fs"
import { join, dirname } from "node:path"
import { fileURLToPath } from "node:url"
import { homedir } from "node:os"

const __dirname = dirname(fileURLToPath(import.meta.url))
const skillBase = join(__dirname, "src", "eastmoney_quant_mcp", "skill")

const skills = [
  { src: join(skillBase, "stock-screening", "SKILL.md"),  dir: "eastmoney-quant-stock-screening" },
  { src: join(skillBase, "data-init", "SKILL.md"),         dir: "eastmoney-quant-data-init" },
  { src: join(skillBase, "report-generation", "SKILL.md"), dir: "eastmoney-quant-report-generation" },
  { src: join(skillBase, "SKILL.md"),                      dir: "eastmoney-quant" },
]

const home = homedir()
const targetRoots = [join(home, ".claude", "skills"), join(home, ".agents", "skills")]

for (const root of targetRoots) {
  for (const skill of skills) {
    if (!existsSync(skill.src)) continue
    try {
      const destDir = join(root, skill.dir)
      mkdirSync(destDir, { recursive: true })
      copyFileSync(skill.src, join(destDir, "SKILL.md"))
      console.log(`[eastmoney-quant] ${skill.dir} → ${destDir}`)
    } catch {
      // silently skip unavailable targets
    }
  }
}
