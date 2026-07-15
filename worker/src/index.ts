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
  TELEGRAM_BOT_TOKEN?: string;
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
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="notes">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-180.png">
<link rel="icon" type="image/png" href="/icon-192.png">
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

.ex{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin:1.4rem 0 0}
.ex span{font-family:var(--mono);font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);margin-right:.2rem}
.ex button{background:none;border:1px solid var(--line);color:var(--muted);border-radius:999px;
  padding:.3rem .65rem;font:inherit;font-size:.78rem;cursor:pointer;
  transition:border-color .15s,color .15s}
.ex button:hover{border-color:var(--amber);color:var(--amber)}
.answer{font-size:15px;line-height:1.65;color:var(--vellum);background:var(--ink2);
  border:1px solid var(--line);border-left:2px solid var(--amber);border-radius:0 12px 12px 0;
  padding:1rem 1.1rem;margin:0 0 1.4rem}
.answer b{color:#fff}
.recent{margin:2.6rem 0 0}
.recent h2{font-family:var(--mono);font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);font-weight:400;margin:0 0 .7rem}
.rc{display:block;padding:.75rem 0;border-bottom:1px solid var(--line)}
.rc:last-child{border-bottom:0}
.rc b{display:block;font-weight:400;font-size:.92rem;color:var(--vellum);line-height:1.45}
.rc i{font-style:normal;display:block;margin:.3rem 0 .25rem;font-size:.8rem;color:var(--sage)}
.rc time{font-family:var(--mono);font-size:.62rem;color:var(--faint)}
.foot{margin:2.4rem 0 0;padding:1rem 0 0;border-top:1px solid var(--line);text-align:center;
  font-family:var(--mono);font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;
  color:var(--faint)}
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
    <p class="hint" id="hint">⌘+enter · searches meaning, not keywords</p>
  </div>

  <div id="out"></div>

  <div class="ex" id="ex">
    <span>try</span>
    <button onclick="fill(this)">what did I decide about kubernetes</button>
    <button onclick="fill(this)">notes about the hackathon</button>
    <button onclick="fill(this)">what am I putting off</button>
  </div>

  <section class="recent">__RECENT__</section>
  <footer class="foot">__STATS__</footer>
</div>
<script>
function fill(b){ const q=document.getElementById('q'); q.value=b.textContent; q.focus(); }
let M='ask';
const $=(i)=>document.getElementById(i);
function mode(m){
  M=m;
  $('mAsk').setAttribute('aria-selected',m==='ask');
  $('mCap').setAttribute('aria-selected',m==='capture');
  $('go').textContent = m==='ask'?'Ask my notes':'Capture it';
  $('q').placeholder = m==='ask'?'what did I decide about…':'a thought, a todo, anything…';
  $('hint').textContent = m==='ask'
    ? '⌘+enter · answers from your notes, with sources'
    : '⌘+enter · lands in your list within seconds';
  $('out').innerHTML='';
  document.getElementById('ex').style.display = m==='ask' ? '' : 'none';
  $('q').focus();
}
$('q').addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key==='Enter')send();});
function esc(s){const d=document.createElement('div');d.textContent=s==null?'':s;return d.innerHTML;}
function fmt(s){return esc(s).replace(/\\*\\*(.+?)\\*\\*/g,'<b>$1</b>').replace(/\\n/g,'<br>');}
async function send(){
  const v=$('q').value.trim(); if(!v) return;
  $('go').disabled=true;
  $('out').innerHTML='<div class="thinking"><span class="nib"></span>'+(M==='ask'?'reading your notes…':'filing it…')+'</div>';
  try{
    if(M==='ask'){
      const r=await fetch('/app/ask?q='+encodeURIComponent(v));
      // Without this an error falls through to hits=[] and the page says your notes
      // don't mention it — telling you something false about your own vault.
      if(!r.ok) throw new Error('search is down (HTTP '+r.status+')');
      const d=await r.json();
      const hits=d.hits||[];
      const answer=(d.answer||'').trim();
      if(!answer && !hits.length){$('out').innerHTML='<p class="empty">Nothing in your notes touches that — yet.</p>';}
      else{
        var html = answer ? '<div class="answer">'+fmt(answer)+'</div>' : '';
        if(hits.length){
          html += '<div class="lede">'+(answer?'from these notes':hits.length+' related notes')+'</div>'+
            hits.map((h,i)=>
            '<div class="hit" style="animation-delay:'+(i*45)+'ms"><div style="flex:1"><div class="t">'+esc(h.title||'untitled')+
            '</div><div class="bar" style="width:'+Math.round((h.score||0)*100)+'%"></div></div>'+
            '<div class="s">'+((h.score||0).toFixed(2))+'</div></div>').join('');
        }
        $('out').innerHTML=html;
      }
    }else{
      const r=await fetch('/app/capture',{method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({text:v})});
      // Saying "Captured" for a failed POST loses the thought silently.
      if(!r.ok) throw new Error("couldn't save that (HTTP "+r.status+")");
      const d=await r.json();
      const todos=d.todos||[];
      $('out').innerHTML='<div class="done"><span>✎</span><div><strong>'+
        (todos.length?'Added to your list':'Captured')+'</strong>'+
        (todos.length?'<ul>'+todos.map(t=>'<li>'+esc(t)+'</li>').join('')+'</ul>'
                     :'<div style="font-size:13px;color:var(--muted);margin-top:4px">It\\'ll become a note on the next sync.</div>')+
        '</div></div>';
      $('q').value='';
    }
  }catch(e){
    const off = !navigator.onLine || /Failed to fetch|NetworkError/i.test(String(e));
    $('out').innerHTML='<p class="err">'+esc(off
      ? (M==='ask' ? "You're offline — can't reach your notes."
                   : "You're offline. Your text is still here; send it when you're back.")
      : String(e && e.message ? e.message : e))+'</p>';
  }
  $('go').disabled=false;
}
</script></body></html>`;

// ── Edge classification + routing (restored — definitions were lost in a merge) ──
const SYSTEM = `You convert a quick captured thought into structured JSON.
Return ONLY JSON: {"title": string, "todos": [{"title": string, "due_date": string|null,
"priority": "none|low|medium|high", "project": string|null}]}
RULES:
- Ticked/done items (\u2713, \u2714, [x], struck-through) are NOT todos.
- NEVER invent todos. If there is nothing actionable, return "todos": [].
- If a TIME is given ("@5pm"), put it in due_date as ISO with that time.`;

async function classify(env: Env, text: string, projects: string[]): Promise<any> {
  if (!env.LLM_API_KEY) return { todos: [] };
  const base = (env.LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const today = new Date().toISOString().slice(0, 10);
  let user = `Today is ${today}. Resolve relative dates against it.`;
  if (projects.length) {
    user += `\nAvailable lists - set todo.project to the EXACT best match or null: ${projects.join(", ")}`;
  }
  user += `\n\n${text}`;
  const r = await fetch(`${base}/chat/completions`, {
    method: "POST",
    headers: { authorization: `Bearer ${env.LLM_API_KEY}`, "content-type": "application/json" },
    body: JSON.stringify({
      model: env.LLM_MODEL || "google/gemini-2.5-flash",
      response_format: { type: "json_object" },
      messages: [{ role: "system", content: SYSTEM }, { role: "user", content: user }],
    }),
  });
  if (!r.ok) return { todos: [] };
  const j: any = await r.json();
  try { return JSON.parse(j.choices[0].message.content); } catch (_) { return { todos: [] }; }
}

const TT = "https://api.ticktick.com/open/v1";
const PRIO: Record<string, number> = { none: 0, low: 1, medium: 3, high: 5 };

async function ttProjects(env: Env): Promise<{ id: string; name: string }[]> {
  if (!env.TICKTICK_TOKEN) return [];
  const r = await fetch(`${TT}/project`, { headers: { authorization: `Bearer ${env.TICKTICK_TOKEN}` } });
  return r.ok ? ((await r.json()) as any[]).map((p) => ({ id: p.id, name: p.name })) : [];
}

const norm = (s: string) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

async function sha1(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

type Created = { title: string; taskId: string; projectId: string | null };

async function routeCapture(env: Env, captureId: string, text: string): Promise<Created[]> {
  const projects = await ttProjects(env);
  const result = await classify(env, text, projects.map((p) => p.name));
  const byNorm = new Map(projects.map((p) => [norm(p.name), p.id]));
  const created: Created[] = [];
  const noteId = `capture:${captureId}`;
  for (const todo of result.todos ?? []) {
    const key = await sha1(`${noteId}:${todo.title}`);
    const seen = await env.DB.prepare("SELECT task_id FROM task_map WHERE key = ?").bind(key).first();
    if (seen) continue;
    const body: any = { title: todo.title, priority: PRIO[todo.priority] ?? 0 };
    const pid = todo.project ? byNorm.get(norm(todo.project)) : undefined;
    if (pid) body.projectId = pid;
    if (todo.due_date) {
      body.dueDate = todo.due_date;
      const time = todo.due_date.includes("T") ? todo.due_date.split("T")[1].slice(0, 8) : "";
      if (time && time !== "00:00:00") { body.isAllDay = false; body.reminders = ["TRIGGER:PT0S"]; }
      else body.isAllDay = true;
    }
    const r = await fetch(`${TT}/task`, {
      method: "POST",
      headers: { authorization: `Bearer ${env.TICKTICK_TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) continue;
    const task: any = await r.json();
    await env.DB.prepare(
      "INSERT OR REPLACE INTO task_map(key,note_id,task_id,project_id,title,completed) VALUES (?,?,?,?,?,0)"
    ).bind(key, noteId, task.id, task.projectId ?? null, todo.title).run();
    created.push({ title: todo.title, taskId: task.id, projectId: task.projectId ?? null });
  }
  if (created.length) {
    await env.DB.prepare("UPDATE captures SET processed=1, reply=? WHERE id=?")
      .bind(created.map((c) => c.title).join("; "), captureId).run();
  }
  return created;
}


const ICON_180 = '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';
const ICON_192 = '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';
const ICON_512 = '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';

/** Send a Markdown message back to a Telegram chat. Returns its message_id. */
async function tgSend(
  env: Env, chatId: number | string, text: string
): Promise<number | null> {
  if (!env.TELEGRAM_BOT_TOKEN) return null;
  const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
  });
  const out: any = await r.json().catch(() => null);
  return out?.result?.message_id ?? null;
}

/** Apply an interpreted correction to the tasks a confirmation created. */
async function applyRefine(
  env: Env, tasks: Created[], fix: any, projects: any[]
): Promise<string> {
  const H = {
    authorization: `Bearer ${env.TICKTICK_TOKEN}`,
    "content-type": "application/json",
  };

  if (fix?.action === "delete") {
    let gone = 0;
    for (const t of tasks) {
      if (!t.projectId) continue;
      const r = await fetch(`${TT}/project/${t.projectId}/task/${t.taskId}`, {
        method: "DELETE", headers: H,
      });
      if (r.ok) {
        gone++;
        await env.DB.prepare("DELETE FROM task_map WHERE task_id = ?").bind(t.taskId).run();
      }
    }
    return gone ? `removed 🗑 ${gone === 1 ? "that todo" : gone + " todos"}` : "couldn't remove that — already gone?";
  }

  if (fix?.action !== "update") {
    return "not sure what to change — try \"tomorrow 6pm\", \"list: Work\", or \"not a todo\".";
  }

  const byNorm = new Map(projects.map((p: any) => [norm(p.name), p.id]));
  const newPid = fix.project ? byNorm.get(norm(fix.project)) : undefined;
  if (fix.project && !newPid) {
    return `no list called "${fix.project}" — your lists: ${projects.map((p: any) => p.name).join(", ")}`;
  }

  const changed: string[] = [];
  for (const t of tasks) {
    const moving = !!newPid && newPid !== t.projectId;
    const body: any = { title: fix.title ?? t.title };
    if (fix.due_date) {
      body.dueDate = fix.due_date;
      const time = fix.due_date.includes("T") ? fix.due_date.split("T")[1].slice(0, 8) : "";
      if (time && time !== "00:00:00") { body.isAllDay = false; body.reminders = ["TRIGGER:PT0S"]; }
      else body.isAllDay = true;
    }

    if (moving) {
      // TickTick's Open API cannot move a task between projects: a cross-project
      // update returns 200 with an EMPTY body and silently does nothing. The only
      // honest move is recreate-in-target + delete-original.
      body.projectId = newPid;
      const mk = await fetch(`${TT}/task`, { method: "POST", headers: H, body: JSON.stringify(body) });
      if (!mk.ok) continue;
      const made: any = await mk.json().catch(() => null);
      if (!made?.id || made.projectId !== newPid) continue;
      if (t.projectId) {
        await fetch(`${TT}/project/${t.projectId}/task/${t.taskId}`, { method: "DELETE", headers: H });
      }
      await env.DB.prepare(
        "UPDATE task_map SET task_id = ?, project_id = ?, title = ? WHERE task_id = ?"
      ).bind(made.id, newPid, body.title, t.taskId).run();
      changed.push(body.title);
      continue;
    }

    body.id = t.taskId;
    body.projectId = t.projectId;
    const r = await fetch(`${TT}/task/${t.taskId}`, {
      method: "POST", headers: H, body: JSON.stringify(body),
    });
    // 200 with an empty body means TickTick ignored the write — don't report success.
    if (!r.ok) continue;
    const back: any = await r.json().catch(() => null);
    if (!back?.id) continue;
    if (fix.title) {
      await env.DB.prepare("UPDATE task_map SET title = ? WHERE task_id = ?")
        .bind(body.title, t.taskId).run();
    }
    changed.push(body.title);
  }
  if (!changed.length) return "couldn't apply that, sorry.";
  const bits: string[] = [];
  if (fix.due_date) bits.push(`due ${fix.due_date.split("T")[0]}`);
  if (fix.project) bits.push(`list ${fix.project}`);
  if (fix.title) bits.push("renamed");
  return `updated ✅ ${changed.join("; ")}${bits.length ? " — " + bits.join(", ") : ""}`;
}

const REFINE_SYSTEM = `You fix a todo that was just created from the user's note.
Given the ORIGINAL text, the TODOS created, and the user's CORRECTION, decide what they meant.
Return JSON: {"action":"delete"|"update"|"none","due_date":string|null,"project":string|null,"title":string|null}
- "delete": they say it isn't a task / was a mistake / already done / drop it.
- "update": they give a new due date, list/project, or wording. Only set fields they actually changed.
- "none": the correction is unclear or asks for something else entirely.
Dates: resolve relative dates against TODAY and return ISO 8601 (YYYY-MM-DDTHH:mm:ss+0000).
Never invent a project that isn't in the provided list.`;

/** Interpret a reply as a correction to the tasks a prior confirmation created. */
async function interpretRefine(
  env: Env, original: string, todos: Created[], correction: string, projects: string[]
): Promise<any> {
  if (!env.LLM_API_KEY) return { action: "none" };
  const today = new Date().toISOString().slice(0, 10);
  const user = [
    `TODAY: ${today}`,
    `PROJECTS: ${projects.join(", ") || "(none)"}`,
    `ORIGINAL: ${original}`,
    `TODOS: ${todos.map((t) => t.title).join("; ")}`,
    `CORRECTION: ${correction}`,
  ].join("\n");
  const base = (env.LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const r = await fetch(`${base}/chat/completions`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.LLM_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: env.LLM_MODEL || "google/gemini-2.5-flash",
      messages: [
        { role: "system", content: REFINE_SYSTEM },
        { role: "user", content: user },
      ],
      response_format: { type: "json_object" },
      temperature: 0,
    }),
  });
  const out: any = await r.json();
  try {
    return JSON.parse(out.choices[0].message.content);
  } catch {
    return { action: "none" };
  }
}

const WHISPER_MODEL = "@cf/openai/whisper";

/** Raw audio bytes -> text. Returns "" when the model gives us nothing usable. */
async function transcribe(env: Env, bytes: ArrayBuffer): Promise<string> {
  const out: any = await env.AI.run(WHISPER_MODEL, {
    audio: [...new Uint8Array(bytes)],
  });
  return (out?.text ?? "").trim();
}

/** Pull a Telegram file (voice note / audio) down to bytes via getFile. */
async function telegramFile(env: Env, fileId: string): Promise<ArrayBuffer | null> {
  const tok = env.TELEGRAM_BOT_TOKEN;
  if (!tok) return null;
  const meta: any = await (
    await fetch(`https://api.telegram.org/bot${tok}/getFile?file_id=${fileId}`)
  ).json();
  const path = meta?.result?.file_path;
  if (!path) return null;
  const r = await fetch(`https://api.telegram.org/file/bot${tok}/${path}`);
  return r.ok ? await r.arrayBuffer() : null;
}


/** Escape for HTML text/attribute context. Worker-side; the `esc` inside APP_PAGE
 *  is browser JS and not in scope here. */
function escHtml(s: string): string {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string
  );
}

const SHARE_CSS = `
:root{--ink:#0b0a09;--ink2:#131110;--line:#26231e;--vellum:#ece5d6;--muted:#8d857a;
  --faint:#5b554c;--amber:#d99a3c;
  --serif:ui-serif,"New York","Iowan Old Style",Palatino,Georgia,serif;
  --round:ui-rounded,"SF Pro Rounded",-apple-system,system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--vellum);font-family:var(--round);
  line-height:1.65;-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;opacity:.05;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
main{position:relative;z-index:1;max-width:44rem;margin:0 auto;padding:clamp(2rem,6vw,4.5rem) 1.5rem 6rem}
h1{font-family:var(--serif);font-weight:500;font-size:clamp(1.9rem,5vw,2.6rem);
  letter-spacing:-.02em;line-height:1.15;margin:0 0 .4rem}
h2,h3{font-family:var(--serif);font-weight:500;letter-spacing:-.01em;margin:2.4rem 0 .6rem}
.eyebrow{font-family:var(--mono);font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--amber);margin:0 0 1.2rem}
hr{border:0;border-top:1px solid var(--line);margin:2.5rem 0}
a{color:var(--amber);text-underline-offset:3px}
blockquote{margin:1.5rem 0;padding:.2rem 0 .2rem 1.1rem;border-left:2px solid var(--amber);
  color:var(--muted);font-style:italic}
code{font-family:var(--mono);font-size:.87em;background:var(--ink2);border:1px solid var(--line);
  border-radius:5px;padding:.1em .35em}
pre{background:var(--ink2);border:1px solid var(--line);border-radius:10px;padding:1rem;
  overflow-x:auto}
pre code{background:none;border:0;padding:0}
img{max-width:100%;height:auto;border-radius:10px;border:1px solid var(--line)}
table{width:100%;border-collapse:collapse;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:.6rem;text-align:left}
ul,ol{padding-left:1.3rem}
li{margin:.3rem 0}
footer{margin-top:4rem;padding-top:1.5rem;border-top:1px solid var(--line);
  font-family:var(--mono);font-size:.72rem;color:var(--faint)}
`;

function sharePage(title: string, html: string): string {
  return `<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b0a09">
<meta name="robots" content="noindex,nofollow,noarchive">
<meta name="referrer" content="no-referrer">
<title>${escHtml(title)}</title>
<style>${SHARE_CSS}
</style>
</head><body><main>
<p class="eyebrow">shared note</p>
<h1>${escHtml(title)}</h1>
<hr>
${html}
<footer>Shared privately via doing2done. This link can be revoked at any time.</footer>
</main></body></html>`;
}

const SHARE_GONE = `<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>Link expired</title>
<style>${SHARE_CSS}</style></head><body><main>
<p class="eyebrow">doing2done</p>
<h1>This link isn't live</h1>
<p style="color:var(--muted)">It was revoked, or it expired. Ask whoever sent it for a fresh one.</p>
</main></body></html>`;

/** Fill the app shell with what's actually in the vault right now.
 *  Rendered server-side: the page proves your captures landed instead of
 *  showing a form floating on a void, and it needs no extra round-trip. */
async function appPage(env: Env): Promise<string> {
  let recent = "";
  let stats = "";
  try {
    const caps = await env.DB.prepare(
      "SELECT text, reply, created FROM captures ORDER BY created DESC LIMIT 5"
    ).all();
    const rows = (caps.results ?? []) as any[];
    if (rows.length) {
      recent =
        "<h2>recently captured</h2>" +
        rows.map((r) => {
          const when = String(r.created ?? "").slice(5, 16).replace("T", " ");
          const became = r.reply
            ? `<i>→ ${escHtml(String(r.reply).split("; ").join(" · "))}</i>`
            : "<i>→ becomes a note on the next sync</i>";
          return `<div class="rc"><b>${escHtml(r.text ?? "")}</b>${became}` +
                 `<time>${escHtml(when)}</time></div>`;
        }).join("");
    }
    const n: any = await env.DB.prepare("SELECT COUNT(*) n FROM notes").first();
    stats = `${n?.n ?? 0} notes searchable`;
  } catch {
    stats = "";  // never let a stats query break capture — the point of the page
  }
  return APP_PAGE.replace("__RECENT__", recent).replace("__STATS__", stats);
}

// ── Remote MCP (JSON-RPC over HTTP) ──
// MCP_TOOLS + mcpHandle were dropped in #31 along with routeCapture; /mcp has
// been returning 500 ever since. Nothing type-checked the worker, so it shipped.
const MCP_TOOLS = [
  {
    name: "ask_notes",
    description: "Semantic search over the user's private note vault. Returns the most relevant notes.",
    inputSchema: {
      type: "object",
      properties: { query: { type: "string", description: "What to look for" } },
      required: ["query"],
    },
  },
  {
    name: "capture",
    description: "Capture a quick thought; it becomes todos + a note on the next sync.",
    inputSchema: {
      type: "object",
      properties: { text: { type: "string", description: "The thought to capture" } },
      required: ["text"],
    },
  },
];

async function mcpHandle(msg: any, env: Env): Promise<any> {
  const { id, method, params } = msg ?? {};
  const ok = (result: unknown) => ({ jsonrpc: "2.0", id, result });
  if (method === "initialize") {
    return ok({
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "doing2done", version: "1.0.0" },
    });
  }
  if (method === "notifications/initialized") return null; // notification: no reply
  if (method === "tools/list") return ok({ tools: MCP_TOOLS });
  if (method === "tools/call") {
    const name = params?.name;
    const args = params?.arguments ?? {};
    let text = "";
    if (name === "ask_notes") {
      const { answer, sources } = await semanticAnswer(env, String(args.query ?? ""));
      const cited = sources.map((h: any) => h.title).join(", ");
      text = (answer || "No matching notes.") + (cited ? `\n\nSources: ${cited}` : "");
    } else if (name === "capture") {
      await storeCapture(env, "mcp", String(args.text ?? ""));
      text = "Captured — it will sync into todos/notes.";
    } else {
      return { jsonrpc: "2.0", id, error: { code: -32601, message: `unknown tool: ${name}` } };
    }
    return ok({ content: [{ type: "text", text }] });
  }
  return { jsonrpc: "2.0", id, error: { code: -32601, message: `unknown method: ${method}` } };
}

const ANSWER_SYSTEM = `You answer a question using ONLY the notes provided. These are
the user's own handwritten/personal notes.
Rules:
- Answer from the notes only. Never add facts that aren't there.
- If the notes don't contain the answer, say exactly: "I don't find that in your notes."
- Be direct and specific — quote the note where it helps.
- Cite the notes you used by their exact title in a "Sources:" line at the end.
- Keep it tight: a few sentences, not an essay.`;

/** Retrieve the most relevant notes, then answer the question grounded in them.
 *  Returns the answer text plus the sources it drew on — the "ask your notes"
 *  promise, which until now only returned a list of titles to go read yourself. */
async function semanticAnswer(env: Env, q: string): Promise<{ answer: string; sources: any[] }> {
  const hits = await semanticAsk(env, q);
  if (!hits.length) {
    return { answer: "I don't find that in your notes.", sources: [] };
  }
  // Pull the bodies of the top matches to ground on. Cap total so the prompt stays sane.
  const top = hits.slice(0, 5);
  const ids = top.map((h: any) => h.note_id);
  const placeholders = ids.map(() => "?").join(",");
  const rows = await env.DB.prepare(
    `SELECT note_id, title, body FROM notes WHERE note_id IN (${placeholders})`
  ).bind(...ids).all();
  const byId = new Map((rows.results ?? []).map((r: any) => [r.note_id, r]));

  let budget = 6000;
  const context = top
    .map((h: any) => {
      const r: any = byId.get(h.note_id);
      if (!r) return "";
      const body = String(r.body || "").slice(0, Math.max(0, budget));
      budget -= body.length;
      return `### ${r.title}
${body}`;
    })
    .filter(Boolean)
    .join("\n\n");

  if (!context.trim() || !env.LLM_API_KEY) {
    return { answer: "I don't find that in your notes.", sources: top };
  }

  const base = (env.LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  try {
    const r = await fetch(`${base}/chat/completions`, {
      method: "POST",
      headers: { authorization: `Bearer ${env.LLM_API_KEY}`, "content-type": "application/json" },
      body: JSON.stringify({
        model: env.LLM_MODEL || "google/gemini-2.5-flash",
        temperature: 0.2,
        messages: [
          { role: "system", content: ANSWER_SYSTEM },
          { role: "user", content: `Question: ${q}\n\nNotes:\n${context}` },
        ],
      }),
    });
    const out: any = await r.json();
    const answer = out?.choices?.[0]?.message?.content?.trim();
    return { answer: answer || "I don't find that in your notes.", sources: top };
  } catch {
    // Retrieval still works even if synthesis fails — hand back the matches.
    return { answer: "", sources: top };
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
   try {
    const url = new URL(req.url);
    const p = url.pathname;

    if (p === "/health") return json({ ok: true, service: "doing2done" });

    // ---- PWA: manifest + icons (public so the OS can fetch them pre-auth) ----
    if (p === "/manifest.webmanifest") {
      return json({
        name: "ask my notes", short_name: "notes", id: "/app",
        start_url: "/app", scope: "/app", display: "standalone",
        background_color: "#0b0a09", theme_color: "#0b0a09",
        description: "Capture a thought or ask your notes.",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      });
    }
    {
      const im = p.match(/^\/icon-(180|192|512)\.png$/);
      if (im) {
        const b64 = im[1] === "180" ? ICON_180 : im[1] === "192" ? ICON_192 : ICON_512;
        const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
        return new Response(bytes, { headers: {
          "content-type": "image/png",
          "cache-control": "public, max-age=604800, immutable",
        }});
      }
    }

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

    // Delete notes that no longer exist in Apple Notes. Nothing else purges the
    // index: a note you deleted stayed searchable in /ask, the bot and MCP forever.
    if (p === "/reconcile" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const b: any = await req.json();
      const live: string[] = Array.isArray(b?.live_ids) ? b.live_ids : [];
      // An empty list would mean "delete everything". A caller that failed to read
      // Apple Notes must not be able to wipe the index by accident.
      if (!live.length) return json({ error: "live_ids required and non-empty" }, 400);

      const rows = await env.DB.prepare("SELECT note_id FROM notes").all();
      const liveSet = new Set(live);
      const gone = (rows.results ?? [])
        .map((r: any) => r.note_id as string)
        .filter((id) => !liveSet.has(id));
      if (!gone.length) return json({ purged: 0 });

      for (const id of gone) {
        await env.DB.prepare("DELETE FROM notes WHERE note_id = ?").bind(id).run();
      }
      try {
        await env.VECTORIZE.deleteByIds(gone.map((id) => id.slice(0, 64)));
      } catch (e: any) {
        // D1 is already clean; report honestly rather than claiming a full purge.
        return json({ purged: gone.length, vectors: "failed", detail: String(e?.message || e) }, 207);
      }
      return json({ purged: gone.length, titles: gone.length });
    }

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
      const todos = (await routeCapture(env, id, b.text ?? "")).map((c) => c.title);   // instant, no Mac round-trip
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
      // ?hits=1 keeps the old retrieval-only shape for callers that want it.
      if (url.searchParams.get("hits") === "only") {
        return json({ query: q, hits: await semanticAsk(env, q) });
      }
      const { answer, sources } = await semanticAnswer(env, q);
      return json({ query: q, answer, hits: sources });
    }

    // ── Gated web app (Cloudflare Access) ──
    if (p === "/app") {
      if (!accessOk(req)) return new Response("Access required", { status: 403 });
      return new Response(await appPage(env), {
        headers: { "content-type": "text/html", "cache-control": "no-store" },
      });
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
      const todos = (await routeCapture(env, id, b.text ?? "")).map((c) => c.title);
      return json({ ok: true, todos });
    }

    // ── Telegram bot (webhook) — capture + ask from your phone, on your own number ──


    // ── Sharing: one note, one unguessable link, revocable ──

    // Public read. Nothing here is listed or discoverable; you need the token.
    if (p.startsWith("/s/")) {
      const token = p.slice(3);
      const row: any = await env.DB.prepare(
        "SELECT title, html, expires_at, revoked FROM shares WHERE token = ?"
      ).bind(token).first();
      const gone = !row || row.revoked
        || (row.expires_at && row.expires_at < new Date().toISOString());
      if (gone) {
        return new Response(SHARE_GONE, {
          status: 404,
          headers: { "content-type": "text/html; charset=utf-8", "x-robots-tag": "noindex" },
        });
      }
      await env.DB.prepare("UPDATE shares SET views = views + 1 WHERE token = ?").bind(token).run();
      return new Response(sharePage(row.title, row.html), {
        headers: {
          "content-type": "text/html; charset=utf-8",
          // A shared link is for a person you sent it to, not for crawlers.
          "x-robots-tag": "noindex, nofollow, noarchive",
          "cache-control": "no-store",
        },
      });
    }

    if (p === "/share" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const b: any = await req.json();
      if (!b?.token || !b?.title || !b?.html) return json({ error: "token, title, html required" }, 400);
      await env.DB.prepare(
        "INSERT OR REPLACE INTO shares(token,note_id,title,html,expires_at) VALUES (?,?,?,?,?)"
      ).bind(b.token, b.note_id ?? null, b.title, b.html, b.expires_at ?? null).run();
      return json({ url: `${url.origin}/s/${b.token}`, expires_at: b.expires_at ?? null });
    }

    if (p === "/shares" && req.method === "GET") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const rows = await env.DB.prepare(
        "SELECT token, title, created_at, expires_at, revoked, views FROM shares ORDER BY created_at DESC"
      ).all();
      return json({ shares: rows.results ?? [] });
    }

    if (p === "/unshare" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const b: any = await req.json();
      const all = b?.all === true;
      const r = all
        ? await env.DB.prepare("UPDATE shares SET revoked = 1 WHERE revoked = 0").run()
        : await env.DB.prepare("UPDATE shares SET revoked = 1 WHERE token = ?").bind(b?.token ?? "").run();
      return json({ revoked: r.meta?.changes ?? 0 });
    }

    // Audio bytes -> text. Bearer-gated; `?capture=1` also files it as a capture.
    if (p === "/transcribe" && req.method === "POST") {
      if (!bearerOk(req, env)) return json({ error: "unauthorized" }, 401);
      const bytes = await req.arrayBuffer();
      if (!bytes.byteLength) return json({ error: "empty body" }, 400);
      let text = "";
      try {
        text = await transcribe(env, bytes);
      } catch (e: any) {
        return json({ error: "transcription failed", detail: String(e?.message || e) }, 502);
      }
      if (!text) return json({ text: "", note: "no speech detected" });
      if (url.searchParams.get("capture") === "1") {
        const id = await storeCapture(env, "voice", text);
        const todos = (await routeCapture(env, id, text)).map((c) => c.title);
        return json({ text, id, todos });
      }
      return json({ text });
    }

    if (p.startsWith("/telegram/") && req.method === "POST") {
      if (p.slice("/telegram/".length) !== env.INGEST_TOKEN) return json({ error: "forbidden" }, 403);
      const upd: any = await req.json();
      const msg = upd.message ?? upd.edited_message;
      const chatId = msg?.chat?.id;
      if (!chatId) return json({ ok: true });

      // Voice note / forwarded audio -> Whisper -> treat exactly like typed text.
      let text = (msg?.text ?? "").trim();
      let viaVoice = false;
      const media = msg?.voice ?? msg?.audio ?? msg?.video_note;
      if (!text && media?.file_id) {
        const bytes = await telegramFile(env, media.file_id);
        if (bytes) {
          try {
            text = await transcribe(env, bytes);
            viaVoice = true;
          } catch {
            text = "";
          }
        }
        if (!text) {
          await tgSend(env, chatId, "Couldn't make out that voice note — try again?");
          return json({ ok: true });
        }
      }
      if (!text) return json({ ok: true });

      let reply: string;
      let created: Created[] = [];
      let captureId = "";
      let captureText = "";
      const low = text.toLowerCase();

      // A reply to one of our confirmations = a correction to those tasks.
      const parent = msg?.reply_to_message?.message_id;
      if (parent) {
        const row: any = await env.DB.prepare(
          "SELECT capture_id, tasks FROM tg_replies WHERE chat_id = ? AND message_id = ?"
        ).bind(String(chatId), parent).first();
        if (row) {
          const tasks: Created[] = JSON.parse(row.tasks);
          const projects = await ttProjects(env);
          const fix = await interpretRefine(
            env, "", tasks, text, projects.map((p: any) => p.name)
          );
          const done = await applyRefine(env, tasks, fix, projects);
          await env.DB.prepare(
            "INSERT INTO corrections(capture_id,original,correction,action,detail) VALUES (?,?,?,?,?)"
          ).bind(
            row.capture_id ?? null,
            tasks.map((x) => x.title).join("; "),
            text,
            fix.action ?? "none",
            JSON.stringify(fix),
          ).run();
          await tgSend(env, chatId, done);
          return json({ ok: true });
        }
      }

      if (text === "/start" || text === "/help") {
        reply = "doing2done ✎\nSend any thought — typed or a voice note — and I'll turn it into todos + a note.\nAsk your notes: `ask what did I decide about X`";
      } else if (low.startsWith("/ask ") || low.startsWith("ask ")) {
        const q = text.replace(/^\/?ask\s+/i, "");
        const { answer, sources } = await semanticAnswer(env, q);
        const cited = sources.slice(0, 4).map((h: any) => h.title).join("\n• ");
        reply = (answer || "Nothing in your notes touches that yet.")
          + (cited ? `\n\n_from:_\n• ${cited}` : "");
      } else {
        const id = await storeCapture(env, viaVoice ? "voice" : "telegram", text);
        created = await routeCapture(env, id, text);
        captureId = id;
        captureText = text;
        reply = created.length
          ? "added ✅\n• " + created.map((c) => c.title).join("\n• ") + "\n\n_reply to fix: \"tomorrow 6pm\", \"list: Work\", \"not a todo\"_"
          : "captured ✎ (will become a note on the next sync)";
        // Voice can mishear; show the transcript so you can catch it.
        if (viaVoice) reply = `_heard:_ "${text}"\n\n` + reply;
      }
      const sent = await tgSend(env, chatId, reply);
      if (sent && created.length) {
        await env.DB.prepare(
          "INSERT OR REPLACE INTO tg_replies(chat_id,message_id,capture_id,tasks) VALUES (?,?,?,?)"
        ).bind(String(chatId), sent, captureId, JSON.stringify(created)).run();
      }
      void captureText;
      return json({ ok: true });
    }

    return new Response("doing2done worker", { status: 200 });
   } catch (e: any) {
    console.error(e?.stack || e);
    return Response.json({ error: "internal error" }, { status: 500 });
   }
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
