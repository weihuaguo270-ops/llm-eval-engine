"""Local A/B blind-review UI for image generation worksheets.

Usage:
  PYTHONPATH=src python examples/serve_image_blind_review.py ^
    --output D:\\agent_learning\\test-temp\\real-image-local-full ^
    --worksheet rater_1.json --rater-id local-reviewer-1
"""

from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>Image blind review</title>
<style>
body{font-family:Segoe UI,sans-serif;margin:24px;background:#111;color:#eee}
.row{display:flex;gap:16px;flex-wrap:wrap}
.card{flex:1;min-width:320px}
img{width:100%;max-width:512px;background:#222}
.prompt{max-width:1080px;line-height:1.4}
button,select,input{font-size:16px;padding:6px 10px}
.nav{margin:16px 0;display:flex;gap:8px;align-items:center}
.ok{color:#8f8}
</style>
</head>
<body>
<h1>Blind image review</h1>
<p class="prompt" id="meta"></p>
<p class="prompt" id="prompt"></p>
<div class="row">
  <div class="card"><h2>A</h2><img id="imgA" alt="A"/><p>scores A
    <input id="a_prompt_adherence" type="number" min="1" max="5" value="4"/>
    <input id="a_visual_quality" type="number" min="1" max="5" value="4"/>
    <input id="a_preference" type="number" min="1" max="5" value="4"/>
    <input id="a_safety" type="number" min="1" max="5" value="5"/>
  </p></div>
  <div class="card"><h2>B</h2><img id="imgB" alt="B"/><p>scores B
    <input id="b_prompt_adherence" type="number" min="1" max="5" value="4"/>
    <input id="b_visual_quality" type="number" min="1" max="5" value="4"/>
    <input id="b_preference" type="number" min="1" max="5" value="4"/>
    <input id="b_safety" type="number" min="1" max="5" value="5"/>
  </p></div>
</div>
<div class="nav">
  <label>preference
    <select id="pref"><option value="a">A</option><option value="b">B</option><option value="tie">tie</option></select>
  </label>
  <button id="save">Save + next</button>
  <button id="prev">Prev</button>
  <span id="status" class="ok"></span>
</div>
<script>
const DIMS=["prompt_adherence","visual_quality","preference","safety"];
let data={entries:[], index:0, raterId:"", worksheet:""};
function scores(prefix){
  const out={};
  DIMS.forEach(d=>out[d]=Number(document.getElementById(prefix+"_"+d).value));
  return out;
}
function fill(prefix, scores){
  DIMS.forEach(d=>document.getElementById(prefix+"_"+d).value=scores[d]||4);
}
function render(){
  const row=data.entries[data.index];
  if(!row){document.getElementById("meta").textContent="done";return;}
  document.getElementById("meta").textContent=`${data.worksheet}  ${data.index+1}/${data.entries.length}  ${row.entry_id}`;
  document.getElementById("prompt").textContent=row.prompt;
  document.getElementById("imgA").src="/media?path="+encodeURIComponent(row.artifact_a)+"&t="+Date.now();
  document.getElementById("imgB").src="/media?path="+encodeURIComponent(row.artifact_b)+"&t="+Date.now();
  fill("a", row.scores_a||{});
  fill("b", row.scores_b||{});
  document.getElementById("pref").value=row.preference||"a";
}
async function load(){
  const payload=await (await fetch("/api/state")).json();
  data=payload;
  render();
}
document.getElementById("save").onclick=async()=>{
  const row=data.entries[data.index];
  const body={index:data.index, rater_id:data.raterId, preference:document.getElementById("pref").value,
              scores_a:scores("a"), scores_b:scores("b")};
  const res=await (await fetch("/api/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)})).json();
  document.getElementById("status").textContent=`saved ${res.completed}/${res.total}`;
  data.entries=res.entries;
  data.index=Math.min(data.index+1, data.entries.length-1);
  render();
};
document.getElementById("prev").onclick=()=>{data.index=Math.max(0,data.index-1);render();};
load();
</script>
</body>
</html>
"""


def load_rows(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def save_rows(path: Path, rows: list) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def completed_count(rows: list) -> int:
    return sum(
        1
        for row in rows
        if str(row.get("rater_id") or "").strip()
        and row.get("preference") in {"a", "b", "tie"}
        and row.get("scores_a")
        and row.get("scores_b")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worksheet", default="rater_1.json")
    parser.add_argument("--rater-id", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    output = args.output.resolve()
    worksheet = (output / args.worksheet).resolve()
    if not worksheet.is_file():
        raise SystemExit(f"missing worksheet: {worksheet}")
    root = output

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            return

        def _json(self, payload: dict, code: int = 200) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                body = HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/state":
                rows = load_rows(worksheet)
                first = next((i for i, row in enumerate(rows) if not row.get("preference")), 0)
                self._json(
                    {
                        "entries": rows,
                        "index": first,
                        "raterId": args.rater_id,
                        "worksheet": args.worksheet,
                    }
                )
                return
            if parsed.path == "/media":
                query = parse_qs(parsed.query)
                target = Path(query.get("path", [""])[0]).resolve()
                if root not in target.parents and target != root:
                    self.send_error(403)
                    return
                if not target.is_file():
                    self.send_error(404)
                    return
                data = target.read_bytes()
                mime = mimetypes.guess_type(target.name)[0] or "image/png"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/save":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            rows = load_rows(worksheet)
            index = int(payload["index"])
            row = rows[index]
            row["rater_id"] = str(payload["rater_id"])
            row["preference"] = str(payload["preference"])
            row["scores_a"] = payload["scores_a"]
            row["scores_b"] = payload["scores_b"]
            save_rows(worksheet, rows)
            self._json(
                {
                    "ok": True,
                    "completed": completed_count(rows),
                    "total": len(rows),
                    "entries": rows,
                }
            )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Open http://{args.host}:{args.port}/  worksheet={worksheet.name}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
