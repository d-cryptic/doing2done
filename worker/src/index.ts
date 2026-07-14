export interface Env {
  DB: D1Database;
  LLM_API_KEY?: string;
  LLM_BASE_URL?: string;
  LLM_MODEL?: string;
  TICKTICK_TOKEN?: string;
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  ASSETS: R2Bucket;
  INGEST_TOKEN?: string;
}

const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";
const json = (d: unknown, status = 200) => Response.json(d, { status });

async function embed(env: Env, text: string): Promise<number[]> {
  const out: any = await env.AI.run(EMBED_MODEL, { text: [text.slice(0, 2000)] });
  return out.data[0];
}

function bearerOk(req: Request, env: Env): boolean {
  return !!env.INGEST_TOKEN && req.headers.get("authorization") === `Bearer ${env.INGEST_TOKEN}`;
}
// Cloudflare Access injects this header on gated routes.
function accessOk(req: Request): boolean {
  return !!req.headers.get("cf-access-jwt-assertion");
}

async function semanticAsk(env: Env, q: string) {
  const qv = await embed(env, q);
  const res = await env.VECTORIZE.query(qv, { topK: 8, returnMetadata: true });
  return res.matches.map((m: any) => ({
    note_id: m.id, title: m.metadata?.title, score: Number(m.score.toFixed(3)),
  }));
}

function rid(): string {
  return crypto.randomUUID();
}

async function storeCapture(env: Env, source: string, text: string): Promise<string> {
  const id = rid();
  await env.DB.prepare(
    "INSERT INTO captures(id,source,text,processed) VALUES (?,?,?,0)"
  ).bind(id, source, text).run();
  return id;
}

const APP_PAGE = `<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0b0a09">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>ask my notes</title>
<style>
:root{
  --ink:#0b0a09; --ink2:#131110; --line:#26231e;
  --vellum:#ece5d6; --muted:#8d857a; --faint:#5b554c;
  --amber:#d99a3c; --sage:#8fae86; --rose:#c07a6b;
  --serif:ui-serif,"New York","Iowan Old Style",Palatino,Georgia,serif;
  --round:ui-rounded,"SF Pro Rounded",-apple-system,system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;min-width:0}
textarea,.send,.seg,.hit{max-width:100%}
html,body{margin:0;background:var(--ink);color:var(--vellum);overflow-x:hidden;width:100%}
/* paper grain — inline SVG turbulence, no network */
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
/* lamplight pooling at the top */
body::after{content:"";position:fixed;inset:0 0 auto;height:340px;pointer-events:none;z-index:0;
  background:radial-gradient(120% 100% at 50% -20%,rgba(217,154,60,.13),transparent 70%)}
.wrap{position:relative;z-index:1;width:100%;max-width:min(640px,100%);box-sizing:border-box;margin:0 auto;
  padding:max(28px,env(safe-area-inset-top)) 22px calc(28px + env(safe-area-inset-bottom))}
header{margin:6px 0 26px;animation:rise .5s both}
.kick{font-family:var(--mono);font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--amber)}
h1{font-family:var(--serif);font-weight:500;font-size:clamp(32px,10vw,40px);line-height:1.02;letter-spacing:-.02em;margin:10px 0 6px}
h1 em{font-style:italic;color:var(--amber)}
.sub{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin:0}
/* composer */
.composer{animation:rise .5s .06s both}
.seg{display:inline-flex;gap:2px;padding:3px;border:1px solid var(--line);border-radius:999px;margin-bottom:12px}
.seg button{font-family:var(--round);font-size:13px;font-weight:600;letter-spacing:.01em;
  padding:7px 16px;border:0;border-radius:999px;background:transparent;color:var(--muted);cursor:pointer;transition:.18s}
.seg button[aria-selected="true"]{background:var(--vellum);color:var(--ink)}
.field{position:relative;width:100%}
textarea{display:block;width:100%;max-width:100%;min-height:104px;resize:none;font-family:var(--round);font-size:17px;line-height:1.45;
  color:var(--vellum);background:var(--ink2);border:1px solid var(--line);border-radius:14px;padding:15px;
  outline:none;transition:border-color .2s,box-shadow .2s}
textarea::placeholder{color:var(--faint)}
textarea:focus{border-color:#3d382f;box-shadow:0 0 0 4px rgba(217,154,60,.07)}
.send{display:block;width:100%;margin-top:10px;font-family:var(--round);font-weight:700;font-size:15.5px;letter-spacing:.01em;
  padding:14px;border:0;border-radius:13px;background:var(--amber);color:#1a1206;cursor:pointer;
  transition:transform .12s,opacity .2s,filter .2s}
.send:active{transform:scale(.985)}
.send:hover{filter:brightness(1.05)}
.send[disabled]{opacity:.5}
.hint{font-family:var(--mono);font-size:10.5px;color:var(--faint);margin:9px 2px 0}
/* results */
#out{margin-top:26px}
.thinking{font-family:var(--mono);font-size:12px;color:var(--muted);display:flex;align-items:center;gap:9px}
.nib{width:7px;height:7px;border-radius:50%;background:var(--amber);animation:pulse 1.05s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:.25;transform:scale(.8)}50%{opacity:1;transform:scale(1.15)}}
.lede{font-family:var(--mono);font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);
  padding-bottom:10px;border-bottom:1px solid var(--line);margin-bottom:4px}
.hit{display:flex;align-items:baseline;gap:12px;padding:14px 2px;border-bottom:1px solid var(--line);
  animation:rise .4s both}
.hit .t{font-family:var(--serif);font-size:17px;line-height:1.3;flex:1}
.hit .s{font-family:var(--mono);font-size:11px;color:var(--faint);font-variant-numeric:tabular-nums}
.bar{height:2px;background:var(--amber);border-radius:2px;opacity:.55;margin-top:5px}
.done{font-family:var(--round);font-size:16px;color:var(--sage);display:flex;gap:9px;align-items:flex-start;
  padding:15px;border:1px solid rgba(143,174,134,.28);border-radius:12px;background:rgba(143,174,134,.05);
  animation:rise .4s both}
.done ul{margin:6px 0 0;padding-left:16px;color:var(--vellum);font-size:14px}
.empty{font-family:var(--serif);font-style:italic;color:var(--faint);font-size:16px;padding:8px 2px}
.err{font-family:var(--mono);font-size:12px;color:var(--rose)}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<div class="wrap">
  <header>
    <div class="kick">doing2done</div>
    <h1>ask your <em>notes</em></h1>
    <p class="sub">everything you ever scribbled — one question away</p>
  </header>

  <div class="composer">
    <div class="seg" role="tablist">
      <button id="mAsk" role="tab" aria-selected="true" onclick="mode('ask')">Ask</button>
      <button id="mCap" role="tab" aria-selected="false" onclick="mode('capture')">Capture</button>
    </div>
    <div class="field">
      <textarea id="q" placeholder="what did I decide about…" autofocus></textarea>
    </div>
    <button class="send" id="go" onclick="send()">Ask my notes</button>
    <p class="hint" id="hint">⌘/ctrl + enter to send · searches meaning, not keywords</p>
  </div>

  <div id="out"></div>
</div>
<script>
let M='ask';
const $=(i)=>document.getElementById(i);
function mode(m){
  M=m;
  $('mAsk').setAttribute('aria-selected',m==='ask');
  $('mCap').setAttribute('aria-selected',m==='capture');
  $('go').textContent = m==='ask'?'Ask my notes':'Capture it';
  $('q').placeholder = m==='ask'?'what did I decide about…':'a thought, a todo, anything…';
  $('hint').textContent = m==='ask'
    ? '⌘/ctrl + enter to send · searches meaning, not keywords'
    : '⌘/ctrl + enter to send · todos land in your list within seconds';
  $('out').innerHTML=''; $('q').focus();
}
$('q').addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter')send();});
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
async function send(){
  const v=$('q').value.trim(); if(!v) return;
  $('go').disabled=true;
  $('out').innerHTML='<div class="thinking"><span class="nib"></span>'+(M==='ask'?'reading your notes…':'filing it…')+'</div>';
  try{
    if(M==='ask'){
      const r=await fetch('/app/ask?q='+encodeURIComponent(v));
      const d=await r.json();
      const hits=d.hits||[];
      if(!hits.length){$('out').innerHTML='<p class="empty">Nothing in your notes touches that — yet.</p>';}
      else{
        $('out').innerHTML='<div class="lede">'+hits.length+' related notes</div>'+hits.map((h,i)=>
          '<div class="hit" style="animation-delay:'+(i*45)+'ms"><div style="flex:1"><div class="t">'+esc(h.title||'untitled')+
          '</div><div class="bar" style="width:'+Math.round((h.score||0)*100)+'%"></div></div>'+
          '<div class="s">'+((h.score||0).toFixed(2))+'</div></div>').join('');
      }
    }else{
      const r=await fetch('/app/capture',{method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({text:v})});
      const d=await r.json();
      const todos=d.todos||[];
      $('out').innerHTML='<div class="done"><span>✎</span><div><strong>'+
        (todos.length?'Added to your list':'Captured')+'</strong>'+
        (todos.length?'<ul>'+todos.map(t=>'<li>'+esc(t)+'</li>').join('')+'</ul>'
                     :'<div style="font-size:13px;color:var(--muted);margin-top:4px">It\\'ll become a note on the next sync.</div>')+
        '</div></div>';
      $('q').value='';
    }
  }catch(e){ $('out').innerHTML='<p class="err">failed — '+esc(String(e))+'</p>'; }
  $('go').disabled=false;
}
</script></body></html>`;

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const p = url.pathname;

    if (p === "/health") return json({ ok: true, service: "doing2done" });

    // Remote MCP endpoint (bearer-gated, same token)
    if (p === "/mcp" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const body = await req.json();
      if (Array.isArray(body)) {
        const out = [];
        for (const m of body) {
          const r = await mcpHandle(m, env);
          if (r) out.push(r);
        }
        return json(out);
      }
      const r = await mcpHandle(body, env);
      return r ? json(r) : new Response(null, { status: 202 });
    }

    // ── Mac thin-agent: bulk note push (existing) ──
    if (p === "/ingest" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const notes = (await req.json()) as Array<{ note_id: string; title: string; body: string; modified: string }>;
      const vectors = [];
      for (const nt of notes) {
        await env.DB.prepare(
          "INSERT OR REPLACE INTO notes(note_id,title,body,modified,updated_at) VALUES (?,?,?,?,datetime('now'))"
        ).bind(nt.note_id, nt.title ?? "", nt.body ?? "", nt.modified ?? "").run();
        try {
          const values = await embed(env, `${nt.title}\n${nt.body}`);
          vectors.push({ id: nt.note_id.slice(0, 64), values, metadata: { title: nt.title } });
        } catch (_) {}
      }
      if (vectors.length) await env.VECTORIZE.upsert(vectors);
      return json({ ingested: notes.length, embedded: vectors.length });
    }

    // ── Capture intake (Shortcuts, and shared by other channels) ──
    if (p === "/capture" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const b = (await req.json()) as { source?: string; text: string };
      const id = await storeCapture(env, b.source ?? "shortcut", b.text ?? "");
      const todos = await routeCapture(env, id, b.text ?? "");   // instant, no Mac round-trip
      return json({ id, todos });
    }
    // Mac pulls pending captures, classifies, then acks.
    if (p === "/captures/pending") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const { results } = await env.DB.prepare(
        "SELECT id,source,text FROM captures WHERE processed=0 ORDER BY created LIMIT 50"
      ).all();
      return json({ captures: results });
    }
    if (p === "/captures/ack" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const { ids } = (await req.json()) as { ids: string[] };
      for (const id of ids) await env.DB.prepare("UPDATE captures SET processed=1 WHERE id=?").bind(id).run();
      return json({ acked: ids.length });
    }

    // ── Ask (bearer for Shortcuts/Mac) ──
    if (p === "/ask") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const q = url.searchParams.get("q") ?? "";
      if (!q) return json({ error: "missing q" }, 400);
      return json({ query: q, hits: await semanticAsk(env, q) });
    }

    // ── Gated web app (Cloudflare Access) ──
    if (p === "/app") {
      if (!accessOk(req)) return new Response("Access required", { status: 403 });
      return new Response(APP_PAGE, { headers: { "content-type": "text/html" } });
    }
    if (p === "/app/ask") {
      if (!accessOk(req)) return json({ error: "forbidden" }, 403);
      const q = url.searchParams.get("q") ?? "";
      return json({ query: q, hits: await semanticAsk(env, q) });
    }
    if (p === "/app/capture" && req.method === "POST") {
      if (!accessOk(req)) return json({ error: "forbidden" }, 403);
      const b = (await req.json()) as { text: string };
      const id = await storeCapture(env, "web", b.text ?? "");
      const todos = await routeCapture(env, id, b.text ?? "");
      return json({ ok: true, todos });
    }

    // ── WhatsApp via Twilio sandbox (form-encoded webhook) ──
    if (p.startsWith("/whatsapp/") && req.method === "POST") {
      if (p.slice("/whatsapp/".length) !== env.INGEST_TOKEN) return json({ error: "forbidden" }, 403);
      const form = await req.formData();
      const body = String(form.get("Body") ?? "").trim();
      let reply = "captured ✅";
      if (body.toLowerCase().startsWith("ask ")) {
        const hits = await semanticAsk(env, body.slice(4));
        const titles = hits.map((h: any) => h.title).filter(Boolean).slice(0, 5);
        reply = titles.length ? "Related: " + titles.join("; ") : "No matches.";
      } else {
        const id = await storeCapture(env, "whatsapp", body);
        const todos = await routeCapture(env, id, body);
        reply = todos.length ? `added ✅ ${todos.join("; ")}` : "captured ✅";
      }
      return new Response(
        `<?xml version="1.0" encoding="UTF-8"?><Response><Message>${reply}</Message></Response>`,
        { headers: { "content-type": "text/xml" } }
      );
    }

    return new Response("doing2done worker", { status: 200 });
  },

  // ── Email capture (Cloudflare Email Routing → this Worker) ──
  async email(message: any, env: Env): Promise<void> {
    const subject = message.headers.get("subject") ?? "";
    let text = subject;
    try {
      const raw = await new Response(message.raw).text();
      text = `${subject}\n${raw}`.slice(0, 4000);
    } catch (_) {}
    await storeCapture(env, "email", text);
  },
};
