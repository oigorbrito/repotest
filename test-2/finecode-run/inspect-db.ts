import { DatabaseSync } from "node:sqlite";
const db = new DatabaseSync(process.argv[2], { readOnly: true });
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%task%'").all();
console.log("tables:", tables.map((t: any) => t.name).join(", "));
for (const t of tables as any[]) {
  for (const row of db.prepare(`SELECT id, status, record FROM ${t.name}`).all() as any[]) {
    const rec = JSON.parse(row.record);
    console.log(t.name, "id", row.id, "status", row.status, "state", JSON.stringify(rec.state), "memos", JSON.stringify(rec.memos ?? null), "restarts", rec.restarts ?? 0);
  }
}
db.close();
