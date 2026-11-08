"""学位罗盘 Compass · 学龄人口与师资缺口推演体（可登录演示服务）

评审账号 judge / learn2026。仅本地运行，不采集任何个人信息。
"""
from __future__ import annotations

import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ACCOUNT = os.environ.get("AGENT_ACCOUNT", "judge")
PASSWORD = os.environ.get("AGENT_PASSWORD", "learn2026")
MAX_BODY = 1 << 20
SESSION_TTL = float(os.environ.get("SESSION_TTL", "28800"))
LOGIN_LIMIT, LOGIN_WINDOW = 10, 60
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "").lower() in ("1", "true")
SESSIONS: dict[str, float] = {}
LOGIN_HITS: dict[str, list[float]] = {}
RESULT_CACHE: dict[tuple, dict] = {}
CACHE_MAX = 200
STATE: dict = {"ready": False}

LOGIN_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>学位罗盘 | 评审登录</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f6f8fb;color:#16202e;font-family:"Microsoft YaHei",sans-serif;font-size:14px}
.w{max-width:420px;margin:11vh auto;padding:0 20px}h1{font-size:20px;font-weight:600;margin:0 0 6px;color:#14507a}
p{color:#4a5568;font-size:13px;line-height:1.7;margin:0 0 22px}.c{background:#fff;border:1px solid #d6dce5;border-radius:10px;padding:24px}
label{display:block;font-size:12px;color:#4a5568;margin:0 0 6px}input{width:100%;padding:10px 12px;border:1px solid #d6dce5;border-radius:6px;font-size:14px;margin-bottom:16px;font-family:inherit}
button{width:100%;padding:10px;background:#14507a;color:#fff;border:0;border-radius:6px;font-size:14px;cursor:pointer}
.e{color:#d9534f;font-size:12px;min-height:16px;margin-top:8px}.h{font-size:12px;color:#8b97a8;line-height:1.7;margin-top:16px}</style></head>
<body><div class="w"><h1>学位罗盘 Compass</h1><p>学龄人口与师资缺口推演体<br>评审演示入口</p>
<div class="c"><form method="post" action="/api/login"><label>评审账号</label><input name="account" value="judge">
<label>密码</label><input name="password" type="password"><button type="submit">进入智能体</button></form>
<div class="e" id="e"></div><div class="h">账号密码随作品说明提交。系统离线运行，数据来自教育部公开统计。</div></div></div></body></html>"""

APP_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>学位罗盘 Compass | 演示</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f6f8fb;color:#16202e;font-family:"Microsoft YaHei",sans-serif;font-size:13px;line-height:1.65}
header{background:#fff;border-bottom:2px solid #14507a;padding:12px 20px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
h1{font-size:16px;font-weight:600;margin:0;color:#14507a}.meta{font-size:11px;color:#8b97a8}
main{max-width:1180px;margin:0 auto;padding:18px 20px;display:grid;grid-template-columns:270px minmax(0,1fr);gap:16px}
@media(max-width:780px){main{grid-template-columns:1fr}}
.panel{background:#fff;border:1px solid #d6dce5;border-radius:10px;padding:14px}h2{font-size:13px;font-weight:600;margin:0 0 10px;color:#14507a}
select,input.q{padding:8px 10px;border:1px solid #d6dce5;border-radius:6px;font-family:inherit;font-size:12px;width:100%;margin-bottom:8px}
.ex{padding:8px 10px;margin-bottom:6px;border-radius:6px;background:#f6f8fb;cursor:pointer;font-size:12px;border-left:3px solid #2f7fb8}.ex:hover{background:#e8f2f8}
button.go{padding:9px 18px;background:#14507a;color:#fff;border:0;border-radius:6px;cursor:pointer;font-family:inherit;font-size:13px}
.bar{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}input.q{flex:1;min-width:180px;width:auto;margin:0}
.concl{background:#eaf3fa;border-left:4px solid #14507a;border-radius:6px;padding:10px 12px;margin-bottom:10px;font-size:14px;font-weight:600;color:#0f3a5c;line-height:1.55}
.concl b{color:#14507a}.card{border:1px solid #d6dce5;border-radius:8px;padding:12px;margin-bottom:10px}
.kv{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}.kv span{background:#e8f2f8;color:#14507a;border-radius:5px;padding:3px 9px;font-size:12px}
.kv .warn{background:#fdecea;color:#c0392b}.kv .ok{background:#e8f6ee;color:#1e7d4f}
.sec{font-size:12px;color:#4a5568;font-weight:600;margin:10px 0 6px}
.ev{border-left:2px solid #2f7fb8;padding:4px 0 4px 10px;margin-bottom:7px;font-size:12px}
ul{margin:4px 0;padding-left:18px}li{margin-bottom:3px}details{margin-top:8px}summary{cursor:pointer;font-size:12px;color:#4a5568}
pre{white-space:pre-wrap;word-break:break-word;background:#f6f8fb;padding:10px;border-radius:6px;font-size:11px;max-height:250px;overflow:auto}
.foot{font-size:11px;color:#8b97a8;margin-top:12px}table{width:100%;border-collapse:collapse;font-size:12px}td,th{border-bottom:1px solid #e5e7eb;padding:5px 6px;text-align:left}th{color:#14507a}</style></head><body>
<header><h1>学位罗盘 Compass · 学龄人口与师资缺口推演体</h1><div><span class="meta" id="m">加载中…</span> <a href="#" onclick="out()" style="font-size:12px;color:#4a5568">退出</a></div></header>
<main><div><div class="panel"><h2>推演条件</h2>
<select id="prov"></select><select id="stage"><option value="junior">初中</option><option value="primary">小学</option></select>
<select id="year"></select><select id="scen"><option>基准</option><option>温和</option><option>加速</option></select></div>
<div class="panel" style="margin-top:12px"><h2>示例问题</h2><div id="ex"></div></div>
<div class="panel" style="margin-top:12px"><h2>推演链条</h2><div style="font-size:12px;color:#4a5568">
① 定位（省/学段/年/情景）<br>② 队列递推求在校生<br>③ 标准编制口径算缺口<br>④ 全国对标定性质<br>⑤ 措施库给动作</div></div></div>
<div class="panel"><div class="bar"><input class="q" id="q" placeholder="例如：广东 2030 年初中教师够不够？"><button class="go" onclick="ask()">开始推演</button></div>
<div id="out"></div><div class="foot">数据：教育部《2024 年教育统计数据》分省表（31 省）与《2025 年全国教育事业发展统计公报》。结论为规划参考。</div></div></main>
<script>let P=[],Q=[];
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function init(){const c=await(await fetch('/api/config')).json();Q=c.prompts;
 document.getElementById('prov').innerHTML=c.provinces.map(x=>`<option>${x}</option>`).join('');
 document.getElementById('year').innerHTML=c.years.map(y=>`<option ${y===2030?'selected':''}>${y}</option>`).join('');
 document.getElementById('ex').innerHTML=Q.map((e,i)=>`<div class="ex" onclick="setQ(${i})">${i+1}. ${esc(e)}</div>`).join('');
 document.getElementById('q').value=Q[0];
 const m=await(await fetch('/api/metrics')).json();
 document.getElementById('m').textContent=`全国小学 ${m.enrol_p_2024} 万 → ${m.enrol_p_2030} 万（${m.change_pct}%）· 初中 ${m.enrol_j_2024} 万 → ${m.enrol_j_2030} 万`;
 if(location.search.indexOf('auto=1')>=0){setTimeout(()=>ask(),1200);}}
function setQ(i){document.getElementById('q').value=Q[i]}
async function ask(){const q=document.getElementById('q').value;
 const body={question:q,province:document.getElementById('prov').value,stage:document.getElementById('stage').value,
  year:parseInt(document.getElementById('year').value),scenario:document.getElementById('scen').value};
 document.getElementById('out').innerHTML='<div class="card">推演中…</div>';
 const r=await(await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json();
 if(r.error){document.getElementById('out').innerHTML='<div class="card">'+esc(r.error)+'</div>';return}
 if(r.answer_type==='compare'){
  const rows=r.rows.map(x=>`<tr><td>${esc(x.province)}</td><td>${x.enrol_wan}</td><td>${x.gap_wan}</td><td>${esc(x.verdict)}</td><td>${x.shift_wan}</td></tr>`).join('');
  document.getElementById('out').innerHTML=`
   <div class="concl">${esc(r.answer_text)}</div>
   <div class="card"><div class="sec">已解析</div><div>${esc(r.parsed_text)}</div>
   <div class="sec">对比</div><table><tr><th>省</th><th>在校生（万）</th><th>缺口（万）</th><th>判定</th><th>需转岗（万）</th></tr>${rows}</table></div>
   <div class="card"><details><summary>展开完整 JSON</summary><pre>${esc(JSON.stringify(r,null,1))}</pre></details></div>`;
  return;
 }
 const s=r.summary,gap=s.gap_wan;
 const cls=s.verdict==='紧缺'?'warn':(s.verdict==='富余'?'ok':'');
 const rows=r.structure.map(x=>`<tr><td>${esc(x.grade)}</td><td>${x.students}</td></tr>`).join('');
 const steps=r.trace.map(t=>`<div class="ev"><b>${t.step}. ${esc(t.action)}</b> <span style="color:#8b97a8">(${esc(t.action_source)})</span><br>${esc(t.observation)}</div>`).join('');
 const acts=r.actions.map(m=>`<li><b>${esc(m.name)}</b>（${esc(m.owner)}，${esc(m.evidence)} 级）：${esc(m.action)}<br><span style="color:#8b97a8">前提：${esc(m.precondition)}；禁忌：${esc(m.taboo)}；指标：${esc(m.metric)}</span></li>`).join('');
 document.getElementById('out').innerHTML=`
 ${r.parsed_text?`<div class="card" style="padding:8px 12px"><span style="color:#8b97a8;font-size:12px">已解析：</span>${esc(r.parsed_text)}</div>`:''}
 <div class="concl">${esc(r.answer_text||('判定：'+s.verdict))}</div>
 <div class="card"><div class="kv"><span class="${cls}">${esc(s.verdict)}</span>
 <span>${esc(r.query.province)} · ${esc(r.query.stage==='junior'?'初中':'小学')} · ${r.query.year} 年 · ${esc(r.query.scenario)}情景</span>
 <span>在校生 ${s.enrol_wan} 万</span><span>较 2024 年 ${s.change_pct}%</span><span>生师比 ${s.ratio}</span></div>
 <div class="sec">教师供需</div>
 <div>现有 ${s.teachers_wan} 万，标准编制需求 ${s.need_std_wan} 万，${gap>=0?'缺口':'富余'} <b>${Math.abs(gap)} 万</b>；
 ${s.shift_wan>=0?'若按现状生师比需增':'若按现状生师比需减'} ${Math.abs(s.shift_wan)} 万</div>
 <div class="sec">全国对标</div>
 <div>全国同阶段${s.national_gap_wan>=0?'缺口':'富余'} ${Math.abs(s.national_gap_wan)} 万；本省占全国在校生 ${(s.share_national*100).toFixed(1)}%</div></div>
 <div class="card"><div class="sec">2024 年分年级结构</div><table><tr><th>年级</th><th>在校生（人）</th></tr>${rows}</table>
 ${r.reasons?`<div class="sec">成因</div><ul>${r.reasons.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
 <div class="sec">推演轨迹</div>${steps}
 <div class="sec">建议动作（措施库，${r.actions.length} 条）</div><ul>${acts}</ul></div>
 <div class="card"><details><summary>展开完整 JSON</summary><pre>${esc(JSON.stringify(r,null,1))}</pre></details></div>`;
 const llm=r.llm;
 if(llm&&llm.text){document.getElementById('out').innerHTML+=`<div class="card"><div class="sec">解释生成（${esc(llm.source)}${llm.model?' · '+esc(llm.model):''}）</div><div class="ev">${esc(llm.text)}</div></div>`}}
async function out(){await fetch('/api/logout',{method:'POST'});location.reload()}
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')ask()});init();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "Compass/1.0"

    def log_message(self, fmt, *args):
        print("[compass] " + fmt % args)

    def _send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "connect-src 'self'; frame-ancestors 'none'")
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def _json(self, obj, code=200, extra=None):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8", extra)

    def _sid(self):
        for p in self.headers.get("Cookie", "").split(";"):
            if p.strip().startswith("sid="):
                return p.strip()[4:]
        return None

    def _client_ip(self) -> str:
        return (self.headers.get("X-Forwarded-For", "") or
                self.client_address[0] or "unknown").split(",")[0].strip()

    def _authed(self):
        s = self._sid()
        if not s:
            return False
        exp = SESSIONS.get(s)
        now = time.time()
        if exp is None or exp < now:
            SESSIONS.pop(s, None)
            return False
        SESSIONS[s] = now + SESSION_TTL
        return True

    def _login_limited(self) -> bool:
        now = time.time()
        hits = [t for t in LOGIN_HITS.get(self._client_ip(), []) if now - t < LOGIN_WINDOW]
        hits.append(now)
        LOGIN_HITS[self._client_ip()] = hits
        return len(hits) > LOGIN_LIMIT

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        q = parse_qs(urlparse(self.path).query)
        if path == "/api/health":
            return self._json({"status": "ok" if STATE.get("ready") else "loading",
                               "ready": bool(STATE.get("ready")),
                               "provinces": len(STATE["data"].provinces) if STATE.get("ready") else 0})
        if path == "/" and q.get("demo") and os.environ.get("DEMO_LOCAL") == "1":
            sid = secrets.token_hex(16)
            SESSIONS[sid] = time.time() + SESSION_TTL
            target = "/?auto=1" if q.get("auto") else "/"
            return self._send(302, "", extra=[("Location", target),
                                              ("Set-Cookie", f"sid={sid}; Path=/; HttpOnly; SameSite=Lax")])
        if path == "/":
            return self._send(200, APP_HTML if self._authed() else LOGIN_HTML)
        if path == "/api/config":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            from core import PROMPTS, SCENARIOS, STAGES, YEARS
            d = STATE["data"]
            return self._json({"provinces": d.provinces, "years": YEARS,
                               "scenarios": SCENARIOS, "stages": STAGES, "prompts": PROMPTS})
        if path == "/api/metrics":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            d = STATE["data"]
            n24, n30 = d.national(2024, "基准"), d.national(2030, "基准")
            return self._json({"enrol_p_2024": n24["enrol_p"], "enrol_p_2030": n30["enrol_p"],
                               "enrol_j_2024": n24["enrol_j"], "enrol_j_2030": n30["enrol_j"],
                               "change_pct": round((n30["enrol_p"] - n24["enrol_p"]) / n24["enrol_p"] * 100, 1),
                               "gap_j_2030": n30["gap_j_std"], "shift_p_2030": n30["shift_p"]})
        if path == "/api/kb":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            from kb import MEASURES, summary
            return self._json({"summary": summary(), "entries": MEASURES})
        if path == "/api/llm/status":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            from llm import status as _st
            return self._json(_st())
        if path == "/api/batch":
            if not self._authed():
                return self._json({"error": "unauthorized"}, 401)
            d = STATE["data"]
            stage = (q.get("stage", ["junior"])[0] or "junior")
            k = "j" if stage == "junior" else "p"
            prov = d.scen["基准"]["summary"]["provinces_2030"]
            rows = sorted(prov, key=lambda z: z[f"gap_{k}_std"], reverse=True)[:10]
            return self._json({"stage": stage, "items": [
                {"province": r["province"], "gap_wan": r[f"gap_{k}_std"]} for r in rows]})
        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            return self._json({"error": "invalid content length"}, 400)
        if length < 0 or length > MAX_BODY:
            try:
                self.rfile.read(min(length, 4 * MAX_BODY))
            except Exception:
                pass
            return self._json({"error": f"payload too large: {length} > {MAX_BODY}"}, 413,
                              extra=[("Connection", "close")])
        raw = self.rfile.read(length).decode("utf-8", errors="replace") if length else ""

        if path == "/api/login":
            if self._login_limited():
                return self._json({"error": "too many attempts, retry in 60s"}, 429)
            f = parse_qs(raw)
            if f.get("account", [""])[0] == ACCOUNT and f.get("password", [""])[0] == PASSWORD:
                sid = secrets.token_hex(16)
                SESSIONS[sid] = time.time() + SESSION_TTL
                https = self.headers.get("X-Forwarded-Proto", "").lower() == "https"
                cookie = f"sid={sid}; Path=/; HttpOnly; SameSite=Lax"
                if COOKIE_SECURE or https:
                    cookie += "; Secure"
                return self._send(302, "", extra=[("Location", "/"), ("Set-Cookie", cookie)])
            return self._send(200, LOGIN_HTML.replace('<div class="e" id="e"></div>',
                                                     '<div class="e" id="e">账号或密码不正确</div>'))
        if path == "/api/logout":
            s = self._sid()
            if s:
                SESSIONS.pop(s, None)
            return self._json({"ok": True})
        if not self._authed():
            return self._json({"error": "unauthorized"}, 401)

        if path == "/api/ask":
            try:
                payload = json.loads(raw or "{}")
            except (json.JSONDecodeError, TypeError):
                return self._json({"error": "invalid json"}, 400)
            if not isinstance(payload, dict):
                return self._json({"error": "payload must be an object"}, 400)
            qtext = payload.get("question", "")
            if not isinstance(qtext, str) or not qtext.strip():
                return self._json({"error": "question 不能为空"}, 400)
            if len(qtext) > 400:
                return self._json({"error": f"question 过长：{len(qtext)} 字，上限 400"}, 400)
            prov = str(payload.get("province") or "")
            stage = str(payload.get("stage") or "junior")
            scen = str(payload.get("scenario") or "基准")
            try:
                year = int(payload.get("year") or 2030)
            except (TypeError, ValueError):
                return self._json({"error": "year 必须是整数"}, 400)
            if not STATE.get("ready"):
                return self._json({"status": "loading", "detail": "模型加载中，请稍候"}, 503)
            key = (prov, stage, year, scen, qtext.strip())
            if key in RESULT_CACHE:
                return self._json({**RESULT_CACHE[key], "cached": True})
            try:
                res = STATE["planner"].answer(qtext.strip(), {
                    "province": prov, "stage": stage, "year": year, "scenario": scen})
            except Exception as exc:  # noqa: BLE001
                return self._json({"error": "execution failed", "detail": type(exc).__name__}, 500)
            try:
                from llm import generate
                res["llm"] = generate(res["evidence"])
            except Exception as exc:  # noqa: BLE001
                res["llm"] = {"source": "fallback", "text": "", "error": type(exc).__name__}
            if len(RESULT_CACHE) >= CACHE_MAX:
                RESULT_CACHE.pop(next(iter(RESULT_CACHE)), None)
            RESULT_CACHE[key] = res
            return self._json(res)
        return self._json({"error": "not found"}, 404)


def init_state(data, planner):
    STATE["data"] = data
    STATE["planner"] = planner
    STATE["ready"] = True


def serve(port: int = 8767, host: str = "127.0.0.1", warmup=None):
    class CappedServer(ThreadingHTTPServer):
        max_concurrent = int(os.environ.get("MAX_CONCURRENCY", "16"))
        _sem = None

        def process_request(self, request, client_address):
            import threading as _th
            if CappedServer._sem is None:
                CappedServer._sem = _th.BoundedSemaphore(CappedServer.max_concurrent)
            if not CappedServer._sem.acquire(timeout=30):
                try:
                    request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
                except Exception:
                    pass
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except Exception:
                CappedServer._sem.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                CappedServer._sem.release()

    httpd = CappedServer((host, port), Handler)
    print(f"[compass] http://{host}:{port}  account={ACCOUNT}", flush=True)
    if warmup is not None:
        try:
            warmup()
        except Exception as exc:  # noqa: BLE001
            print(f"[compass] 加载失败：{type(exc).__name__}: {exc}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[compass] stopped")
