// 给 caddy adapt 产出的 JSON 注入 apps.tls.connection_policies[].default_sni。
// 由 ops/personal.sh 调用：node .inject-default-sni.mjs <in.json> <out.json> <ip>
import { readFileSync, writeFileSync } from "node:fs";

const [inPath, outPath, ip] = process.argv.slice(2);
if (!inPath || !outPath || !ip) {
  console.error("用法: node .inject-default-sni.mjs <in.json> <out.json> <ip>");
  process.exit(1);
}
const cfg = JSON.parse(readFileSync(inPath, "utf8"));
cfg.apps.tls = { connection_policies: [{ default_sni: ip }] };
writeFileSync(outPath, JSON.stringify(cfg, null, 2) + "\n");
console.log(`injected default_sni=${ip} -> ${outPath}`);
