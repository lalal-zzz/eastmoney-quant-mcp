import { homedir } from "node:os"
import { join } from "node:path"

export const userHome = () => process.env.EASTMONEY_QUANT_HOME || homedir()
export const appRoot = () => join(userHome(), ".eastmoney-quant")
export const appConfigPath = () => join(appRoot(), "config.toml")
export const installStatePath = () => join(appRoot(), "install-state.json")
export const runtimePath = () => join(appRoot(), "runtime.json")
export const runtimeDir = () => join(appRoot(), "runtime")
export const backupDir = () => join(appRoot(), "backups")
