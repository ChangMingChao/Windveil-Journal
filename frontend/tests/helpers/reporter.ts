/** OpenLogos reporter（Vitest）。契约见 logos/spec/test-results.md。
 *
 * 与 pytest 侧那份 reporter 的关键区别：**这里只 append，绝不 truncate**。
 * 两个 runner 写同一个 JSONL，谁 truncate 谁就会抹掉另一边的结果。
 * 因此清空文件的职责固定归 pytest（它先跑），前端只往后追加——
 * `verify.pre_run_command` 必须保持「先 pytest 再 vitest」这个顺序。
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const RESULT_PATH =
  process.env.OPENLOGOS_RESULT_PATH ??
  resolve(HERE, "../../../logos/resources/verify/test-results.jsonl");

const ID_RE = /(UT|ST)-S\d{2}-\d{2,3}/;

interface Row {
  id: string;
  status: "pass" | "fail" | "skip";
  duration_ms: number;
  timestamp: string;
  scenario: string;
  error?: string;
}

function collect(tasks: readonly any[], out: Row[]): void {
  for (const task of tasks) {
    if (task.type === "suite") {
      collect(task.tasks ?? [], out);
      continue;
    }
    const match = ID_RE.exec(String(task.name ?? ""));
    if (!match) continue;
    const state = task.result?.state;
    const status: Row["status"] =
      state === "pass" ? "pass" : state === "fail" ? "fail" : "skip";
    const row: Row = {
      id: match[0],
      status,
      duration_ms: Math.round(task.result?.duration ?? 0),
      timestamp: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"),
      scenario: match[0].split("-")[1] ?? "",
    };
    if (status === "fail") {
      row.error = String(task.result?.errors?.[0]?.message ?? "assertion failed").slice(0, 500);
    }
    out.push(row);
  }
}

export default class OpenLogosReporter {
  onFinished(files: any[] = []): void {
    const rows: Row[] = [];
    for (const file of files) collect(file.tasks ?? [], rows);
    if (rows.length === 0) return;
    mkdirSync(dirname(RESULT_PATH), { recursive: true });
    appendFileSync(
      RESULT_PATH,
      rows.map((r) => JSON.stringify(r)).join("\n") + "\n",
      "utf8",
    );
    console.log(`openlogos-reporter: 追加 ${rows.length} 条 → ${RESULT_PATH}`);
  }
}
