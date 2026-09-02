#!/usr/bin/env node
// smoke dispatcher：发现并顺序运行 scripts/smoke-*，把结果汇总到一份 JSONL。
//
// 单一职责：**清空结果文件、按名字顺序跑每个 runner、汇总退出码**。
// 具体断言由各 runner 负责——dispatcher 不认识任何 SMOKE-* ID，
// 因此新增一个 runner 不需要改这里。
//
// 环境变量：
//   OPENLOGOS_SMOKE_RESULT_PATH  结果文件，默认 logos/resources/verify/smoke-results.jsonl
//   SMOKE_ENV / SMOKE_BASE_URL / ...  原样传给各 runner

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const REPO_ROOT = path.resolve(__dirname, "..");
const SCRIPTS_DIR = path.join(REPO_ROOT, "scripts");
const RESULT_PATH =
  process.env.OPENLOGOS_SMOKE_RESULT_PATH ||
  path.join(REPO_ROOT, "logos", "resources", "verify", "smoke-results.jsonl");

// runner 的解释器按扩展名派发。python runner 优先用后端 venv 里的解释器，
// 因为它一定装了项目要求的 Python 版本。
function interpreterFor(file) {
  if (file.endsWith(".js")) return { cmd: process.execPath, args: [file] };
  if (file.endsWith(".sh")) return { cmd: "bash", args: [file] };
  if (file.endsWith(".py")) {
    const venvWin = path.join(REPO_ROOT, "backend", ".venv", "Scripts", "python.exe");
    const venvNix = path.join(REPO_ROOT, "backend", ".venv", "bin", "python");
    const python = fs.existsSync(venvWin)
      ? venvWin
      : fs.existsSync(venvNix)
        ? venvNix
        : process.platform === "win32"
          ? "python"
          : "python3";
    return { cmd: python, args: [file] };
  }
  return null;
}

function discover() {
  return fs
    .readdirSync(SCRIPTS_DIR)
    .filter((name) => name.startsWith("smoke-") && /\.(js|sh|py)$/.test(name))
    .sort()
    .map((name) => path.join(SCRIPTS_DIR, name));
}

function main() {
  const runners = discover();
  if (runners.length === 0) {
    console.error("run-smoke: 在 scripts/ 下没有发现任何 smoke-* runner");
    return 1;
  }

  // 每轮 smoke 从空文件开始：残留的上一轮结果会让覆盖判定看起来通过，实际没跑
  fs.mkdirSync(path.dirname(RESULT_PATH), { recursive: true });
  fs.writeFileSync(RESULT_PATH, "", "utf8");

  let failed = 0;
  for (const file of runners) {
    const rel = path.relative(REPO_ROOT, file);
    const interp = interpreterFor(file);
    if (!interp) {
      console.error(`run-smoke: 不知道如何运行 ${rel}`);
      failed += 1;
      continue;
    }
    console.log(`run-smoke: → ${rel}`);
    const proc = spawnSync(interp.cmd, interp.args, {
      cwd: REPO_ROOT,
      stdio: "inherit",
      env: { ...process.env, OPENLOGOS_SMOKE_RESULT_PATH: RESULT_PATH },
    });
    if (proc.error) {
      console.error(`run-smoke: ${rel} 启动失败：${proc.error.message}`);
      failed += 1;
    } else if (proc.status !== 0) {
      failed += 1;
    }
  }

  const lines = fs
    .readFileSync(RESULT_PATH, "utf8")
    .split("\n")
    .filter((l) => l.trim());
  const tally = { pass: 0, fail: 0, skip: 0 };
  for (const line of lines) {
    try {
      const status = JSON.parse(line).status;
      if (status in tally) tally[status] += 1;
    } catch {
      /* 一行损坏不影响其他行，这正是选 JSONL 的理由 */
    }
  }
  console.log(
    `run-smoke: ${runners.length} 个 runner，${lines.length} 条结果 ` +
      `(pass=${tally.pass} fail=${tally.fail} skip=${tally.skip}) → ` +
      path.relative(REPO_ROOT, RESULT_PATH),
  );
  return failed ? 1 : 0;
}

process.exit(main());
