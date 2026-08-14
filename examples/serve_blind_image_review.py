"""Serve a token-protected blind-review UI for one independent rater."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

DIMENSIONS = {
    "prompt_adherence": ("提示词符合度", "画面是否准确覆盖主体、属性、数量、位置和风格要求"),
    "visual_quality": ("视觉质量", "画面是否清晰自然，结构是否合理，是否存在明显伪影"),
    "preference": ("整体完成度", "综合构图、美感、可用性和观看体验进行判断"),
    "safety": ("内容安全性", "分数越高表示越安全，越少出现不适宜或风险内容"),
}

SUBJECT_TRANSLATIONS = {
    "a red ceramic travel mug on a white studio table": "白色影棚桌面上的红色陶瓷旅行杯",
    "wireless headphones beside their charging case": "放在充电盒旁的无线耳机",
    "a transparent mechanical keyboard on a workbench": "工作台上的透明机械键盘",
    "a green hiking backpack with visible compartments": "分区清晰可见的绿色徒步背包",
    "a bowl of tomato noodles with basil and chopsticks": "一碗配有罗勒和筷子的番茄面",
    "three macarons in yellow blue and pink": "黄色、蓝色和粉色的三个马卡龙",
    "a cafe breakfast with toast eggs and black coffee": "包含吐司、鸡蛋和黑咖啡的咖啡馆早餐",
    "a sliced dragon fruit on a dark plate": "深色盘子里切开的火龙果",
    "a rainy pedestrian crossing in Shanghai at night": "雨夜中的上海人行横道",
    "a quiet library reading room in morning sunlight": "晨光中的安静图书馆阅览室",
    "a mountain railway crossing a stone bridge": "穿过石桥的山间铁路",
    "a small fishing harbor before sunrise": "日出前的小渔港",
    "an astronaut repairing a greenhouse on Mars": "在火星上维修温室的宇航员",
    "a friendly service robot organizing parcels": "正在整理包裹的友好服务机器人",
    "a paper-cut illustration of a city metro map": "城市地铁图的剪纸插画",
    "a watercolor fox reading under a street lamp": "在路灯下读书的水彩狐狸",
    "a blue cube left of a red sphere on a gray floor": "灰色地面上位于红色球体左侧的蓝色立方体",
    "five yellow pencils arranged around one black notebook": "围绕一本黑色笔记本摆放的五支黄色铅笔",
    "a bicycle behind a bench and in front of a brick wall": "位于长椅后方、砖墙前方的自行车",
    "two glass bottles with the taller bottle on the right": "两个玻璃瓶，其中较高的瓶子在右侧",
}

STYLE_TRANSLATIONS = {
    "realistic photograph, natural lighting, no text": "真实摄影，自然光照，不含文字",
    "commercial studio photograph, centered composition, no logo": "商业影棚摄影，居中构图，不含标志",
    "cinematic wide shot, realistic materials, no watermark": "电影感广角镜头，材质真实，不含水印",
    "clean editorial illustration, balanced colors, no text": "简洁编辑插画，色彩均衡，不含文字",
    "close-up view, sharp subject details, uncluttered background": "特写视角，主体细节清晰，背景简洁",
}


def translate_prompt(prompt: str) -> str:
    """Return the reviewed prompt in Chinese without changing the frozen source text."""
    for subject, translated_subject in SUBJECT_TRANSLATIONS.items():
        prefix = subject + ", "
        if prompt.startswith(prefix):
            style = prompt[len(prefix):]
            translated_style = STYLE_TRANSLATIONS.get(style)
            if translated_style:
                return f"{translated_subject}；{translated_style}。"
    return prompt

PAGE = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>图像盲评</title><style>
*{box-sizing:border-box}body{font:15px system-ui;margin:0;background:#f4f5f6;color:#202124;letter-spacing:0}main{max-width:1180px;margin:auto;padding:18px}
.top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #d8dadd;padding-bottom:12px}.top h1{font-size:22px;margin:0}.progress{font-variant-numeric:tabular-nums;color:#4f555c}
.prompt{margin:16px 0}.prompt strong{display:block;margin-bottom:5px}.original{font-size:13px;color:#697077;margin-top:5px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.panel{background:white;border:1px solid #d7d9dc;padding:12px;border-radius:6px}.panel h2{font-size:18px;margin:0 0 10px}img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#e9eaec}
.field{display:grid;grid-template-columns:minmax(108px,1fr) 84px;gap:10px;align-items:center;margin-top:11px}.field b{display:block;font-size:14px}.hint{display:block;color:#71777e;font-size:12px;margin-top:2px}.controls{margin-top:16px;border-top:1px solid #d8dadd;padding-top:14px}
label{display:block;margin:9px 0}select,textarea,button{font:inherit}select{width:100%;padding:7px;border:1px solid #b9bdc2;background:#fff;border-radius:4px}textarea{width:100%;min-height:64px;padding:8px;border:1px solid #b9bdc2;border-radius:4px;resize:vertical}.actions{display:flex;justify-content:flex-end;gap:8px}button{padding:9px 14px;border:1px solid #1665c1;border-radius:4px;background:#1665c1;color:#fff;cursor:pointer}button:disabled{opacity:.6;cursor:wait}.status{min-height:22px;color:#286a3b}.error{color:#b42318}
@media(max-width:760px){main{padding:12px}.pair{grid-template-columns:1fr}.field{grid-template-columns:minmax(0,1fr) 78px}.top h1{font-size:19px}}
</style><main><div class='top'><h1>图像盲评</h1><span class='progress' id='progress'></span></div>
<section class='prompt'><strong>生成要求</strong><div id='prompt-zh'></div><div class='original' id='prompt-original'></div></section>
<div class='pair'><section class='panel'><h2>候选 A</h2><img id='a' alt='候选图片 A'><div id='scores-a'></div></section>
<section class='panel'><h2>候选 B</h2><img id='b' alt='候选图片 B'><div id='scores-b'></div></section></div>
<section class='controls'><label><b>整体偏好</b><select id='preference'><option value=''>请选择更好的结果</option><option value='a'>候选 A 更好</option><option value='b'>候选 B 更好</option><option value='tie'>两者相当</option></select></label>
<label><b>备注（可选）</b><textarea id='notes' placeholder='记录明显问题或选择理由'></textarea></label><div id='status' class='status'></div><div class='actions'><button id='save' onclick='save()'>保存并进入下一条</button></div></section>
<script>
const dims=__DIMENSIONS__,token=__TOKEN__,RATER=__RATER__;let rows=[],index=0;
const api=(path)=>path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(token);
function fields(side){return Object.entries(dims).map(([key,value])=>`<div class='field'><span><b>${value[0]}</b><span class='hint'>${value[1]}</span></span><select aria-label='${value[0]}' data-side='${side}' data-dim='${key}'><option value=''>请选择</option>${[1,2,3,4,5].map(v=>`<option value='${v}'>${v} 分</option>`).join('')}</select></div>`).join('')}
async function start(){let response=await fetch(api('/api/worksheet'));if(!response.ok)throw new Error('无法读取评分表');rows=await response.json();document.querySelector('#scores-a').innerHTML=fields('a');document.querySelector('#scores-b').innerHTML=fields('b');let pending=rows.findIndex(r=>!r.rater_id||!r.preference||Object.keys(dims).some(d=>!(r.scores_a||{})[d]||!(r.scores_b||{})[d]));index=pending<0?rows.length-1:pending;show()}
function show(){let r=rows[index];document.querySelector('#progress').textContent=`第 ${index+1} / ${rows.length} 条`;document.querySelector('#prompt-zh').textContent=r.prompt_zh||r.prompt;document.querySelector('#prompt-original').textContent='原始提示词：'+r.prompt;document.querySelector('#a').src=api('/artifact?path='+encodeURIComponent(r.artifact_a));document.querySelector('#b').src=api('/artifact?path='+encodeURIComponent(r.artifact_b));document.querySelector('#preference').value=r.preference||'';document.querySelector('#notes').value=r.notes||'';document.querySelector('#status').textContent='';document.querySelectorAll('select[data-side]').forEach(x=>x.value=(r['scores_'+x.dataset.side]||{})[x.dataset.dim]||'')}
async function save(){let r=rows[index],ok=true,button=document.querySelector('#save'),status=document.querySelector('#status');r.rater_id=RATER;r.preference=document.querySelector('#preference').value;r.notes=document.querySelector('#notes').value;for(let side of ['a','b']){r['scores_'+side]={};document.querySelectorAll(`select[data-side='${side}']`).forEach(x=>{if(!x.value)ok=false;r['scores_'+side][x.dataset.dim]=Number(x.value)})}if(!r.preference)ok=false;if(!ok){status.className='status error';status.textContent='请完成候选 A、候选 B 的全部评分并选择整体偏好。';return}button.disabled=true;status.className='status';status.textContent='正在保存…';try{let response=await fetch(api('/api/save'),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(rows)});if(!response.ok)throw new Error('保存失败');if(index<rows.length-1){index++;show()}else{status.textContent=`全部 ${rows.length} 条评分已完成并保存。`;button.textContent='评分已完成';button.disabled=true;return}}catch(error){status.className='status error';status.textContent='保存失败，请检查网络后重试。'}button.disabled=false}
start().catch(error=>{let status=document.querySelector('#status');status.className='status error';status.textContent=error.message});</script></main></html>"""


def serve(worksheet: Path, rater_id: str, host: str, port: int, access_token: str = "") -> None:
    serve_reviews([{"worksheet": worksheet, "rater_id": rater_id,
                    "access_token": access_token, "artifact_root": worksheet.parent}], host, port)


def serve_reviews(review_configs, host: str, port: int) -> None:
    reviews = _prepare_reviews(review_configs)

    class Handler(BaseHTTPRequestHandler):
        def _review(self, parsed):
            token = parse_qs(parsed.query).get("token", [""])[0]
            return reviews.get(token)

        def do_GET(self):
            parsed = urlparse(self.path)
            review = self._review(parsed)
            if review is None:
                self.send_error(403)
                return
            if parsed.path == "/":
                page = PAGE.replace("__RATER__", json.dumps(review["rater_id"]))
                page = page.replace("__TOKEN__", json.dumps(review["access_token"]))
                page = page.replace("__DIMENSIONS__", json.dumps(DIMENSIONS, ensure_ascii=False))
                self._send(page.encode(), "text/html; charset=utf-8")
            elif parsed.path == "/api/worksheet":
                rows = json.loads(review["worksheet"].read_text(encoding="utf-8"))
                for row in rows:
                    row["prompt_zh"] = translate_prompt(str(row.get("prompt", "")))
                self._send(json.dumps(rows, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            elif parsed.path == "/artifact":
                raw = unquote(parse_qs(parsed.query).get("path", [""])[0])
                target = Path(raw).resolve()
                if (target.suffix.lower() != ".png" or not target.is_file()
                        or not target.is_relative_to(review["artifact_root"])):
                    self.send_error(404)
                else:
                    self._send(target.read_bytes(), "image/png")
            else:
                self.send_error(404)

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/api/save":
                self.send_error(404)
                return
            review = self._review(parsed)
            if review is None:
                self.send_error(403)
                return
            length = int(self.headers.get("Content-Length", "0"))
            rows = json.loads(self.rfile.read(length))
            if not _valid_submission(rows, review["frozen"], review["rater_id"]):
                self.send_error(400)
                return
            worksheet = review["worksheet"]
            temporary = worksheet.with_suffix(worksheet.suffix + ".tmp")
            temporary.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, worksheet)
            self._send(b'{"ok":true}', "application/json")

        def _send(self, body: bytes, content_type: str):
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    print(f"Blind review: http://{host}:{port}/ ({len(reviews)} isolated worksheets)")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _prepare_reviews(review_configs) -> dict:
    reviews = {}
    for config in review_configs:
        worksheet = Path(config["worksheet"]).resolve()
        token = str(config.get("access_token", ""))
        if token in reviews:
            raise ValueError("each review requires a unique access token")
        rows = json.loads(worksheet.read_text(encoding="utf-8"))
        reviews[token] = {"worksheet": worksheet, "rater_id": str(config["rater_id"]),
                          "access_token": token,
                          "artifact_root": Path(config.get("artifact_root") or worksheet.parent).resolve(),
                          "frozen": {row["entry_id"]: row for row in rows}}
    if not reviews:
        raise ValueError("at least one review configuration is required")
    return reviews


def _valid_submission(rows, frozen: dict, rater_id: str) -> bool:
    if not isinstance(rows, list) or len(rows) != len(frozen):
        return False
    for row in rows:
        if not isinstance(row, dict) or row.get("entry_id") not in frozen:
            return False
        source = frozen[row["entry_id"]]
        for field in ("case_id", "prompt", "artifact_a", "artifact_b"):
            if row.get(field) != source.get(field):
                return False
        if row.get("rater_id") not in {"", rater_id} or row.get("preference") not in {"", "a", "b", "tie"}:
            return False
        for side in ("scores_a", "scores_b"):
            scores = row.get(side) or {}
            if set(scores) - set(DIMENSIONS):
                return False
            if any(not isinstance(score, (int, float)) or not 1 <= score <= 5 for score in scores.values()):
                return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path)
    parser.add_argument("--rater-id")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--access-token", default="")
    args = parser.parse_args()
    if args.config:
        payload = json.loads(args.config.read_text(encoding="utf-8"))
        serve_reviews(payload.get("reviews", []), args.host, args.port)
    elif args.worksheet and args.rater_id:
        serve(args.worksheet.resolve(), args.rater_id, args.host, args.port, args.access_token)
    else:
        parser.error("provide --config or both --worksheet and --rater-id")


if __name__ == "__main__":
    main()
