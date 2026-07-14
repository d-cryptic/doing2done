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

const APP_PAGE = `<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>ask my notes</title>
<style>body{background:#000;color:#eee;font:16px -apple-system,system-ui;margin:0;padding:18px;max-width:720px;margin:auto}
h1{font-size:18px}input,button{font:inherit}#q{width:100%;padding:12px;background:#111;border:1px solid #333;color:#eee;border-radius:8px}
button{margin-top:8px;padding:10px 16px;background:#2a2;border:0;border-radius:8px;color:#000;font-weight:600}
.a{white-space:pre-wrap;margin-top:16px;padding:14px;background:#0c0c0d;border:1px solid #262628;border-radius:8px}
.s{color:#7ec699;font-size:12px;margin-top:8px}.c{margin-top:24px;border-top:1px solid #222;padding-top:16px}</style></head>
<body><h1>ask my notes</h1>
<input id=q placeholder="what did I decide about..." autofocus>
<button onclick="ask()">Ask</button><div id=out></div>
<div class=c><input id=cap placeholder="quick capture a thought..."><button onclick="cap()">Capture</button><div id=capout class=s></div></div>
<script>
async function ask(){const q=document.getElementById('q').value;if(!q)return;
document.getElementById('out').innerHTML='<div class=a>...</div>';
const r=await fetch('/app/ask?q='+encodeURIComponent(q));const d=await r.json();
document.getElementById('out').innerHTML='<div class=a>'+(d.answer||'')+'</div><div class=s>'+(d.sources||[]).join(' . ')+'</div>';}
async function cap(){const t=document.getElementById('cap').value;if(!t)return;
await fetch('/app/capture',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text:t})});
document.getElementById('capout').textContent='captured';document.getElementById('cap').value='';}
</script></body></html>`;


// ── Remote MCP (JSON-RPC over HTTP) — any agent can use doing2done with no install ──
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
      const hits = await semanticAsk(env, String(args.query ?? ""));
      text = hits.length
        ? "Relevant notes:\n" + hits.map((h: any) => `- ${h.title} (${h.score})`).join("\n")
        : "No matching notes.";
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


// ── Edge classification + routing: captures become todos INSTANTLY (no 30-min wait) ──
const SYSTEM = `You convert a quick captured thought into structured JSON.
Return ONLY JSON: {"title": string, "todos": [{"title": string, "due_date": string|null,
"priority": "none|low|medium|high", "project": string|null}]}
RULES:
- Ticked/done items (✓, ✔, [x], struck-through) are NOT todos.
- NEVER invent todos. If there is nothing actionable, return "todos": [].
- If a TIME is given ("@5pm"), put it in due_date as ISO with that time.`;

async function classify(env: Env, text: string, projects: string[]): Promise<any> {
  if (!env.LLM_API_KEY) return { todos: [] };
  const base = (env.LLM_BASE_URL || "https://api.openai.com/v1").replace(/\/$/, "");
  const today = new Date().toISOString().slice(0, 10);
  let user = `Today is ${today}. Resolve relative dates against it.`;
  if (projects.length) {
    user += `\nAvailable lists — set todo.project to the EXACT best match or null: ${projects.join(", ")}`;
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
  try {
    return JSON.parse(j.choices[0].message.content);
  } catch (_) {
    return { todos: [] };
  }
}

const TT = "https://api.ticktick.com/open/v1";
const PRIO: Record<string, number> = { none: 0, low: 1, medium: 3, high: 5 };

async function ttProjects(env: Env): Promise<{ id: string; name: string }[]> {
  if (!env.TICKTICK_TOKEN) return [];
  const r = await fetch(`${TT}/project`, {
    headers: { authorization: `Bearer ${env.TICKTICK_TOKEN}` },
  });
  return r.ok ? ((await r.json()) as any[]).map((p) => ({ id: p.id, name: p.name })) : [];
}

const norm = (s: string) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

async function sha1(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Classify a capture and create the todos in TickTick, deduped via D1. */
async function routeCapture(env: Env, captureId: string, text: string): Promise<string[]> {
  const projects = await ttProjects(env);
  const result = await classify(env, text, projects.map((p) => p.name));
  const byNorm = new Map(projects.map((p) => [norm(p.name), p.id]));
  const created: string[] = [];
  const noteId = `capture:${captureId}`;

  for (const todo of result.todos ?? []) {
    const key = await sha1(`${noteId}:${todo.title}`);
    const seen = await env.DB.prepare("SELECT task_id FROM task_map WHERE key = ?")
      .bind(key).first();
    if (seen) continue; // already routed

    const body: any = { title: todo.title, priority: PRIO[todo.priority] ?? 0 };
    const pid = todo.project ? byNorm.get(norm(todo.project)) : undefined;
    if (pid) body.projectId = pid;
    if (todo.due_date) {
      body.dueDate = todo.due_date;
      const time = todo.due_date.includes("T") ? todo.due_date.split("T")[1].slice(0, 8) : "";
      if (time && time !== "00:00:00") {
        body.isAllDay = false;
        body.reminders = ["TRIGGER:PT0S"];
      } else body.isAllDay = true;
    }
    const r = await fetch(`${TT}/task`, {
      method: "POST",
      headers: { authorization: `Bearer ${env.TICKTICK_TOKEN}`, "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) continue;
    const task: any = await r.json();
    await env.DB.prepare(
      "INSERT OR REPLACE INTO task_map(key,note_id,task_id,project_id,title,completed) " +
      "VALUES (?,?,?,?,?,0)"
    ).bind(key, noteId, task.id, task.projectId ?? null, todo.title).run();
    created.push(todo.title);
  }
  if (created.length) {
    await env.DB.prepare("UPDATE captures SET processed=1, reply=? WHERE id=?")
      .bind(created.join("; "), captureId).run();
  }
  return created;
}

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
      const hits = await semanticAsk(env, q);
      const titles = hits.map((h: any) => h.title).filter(Boolean);
      return json({ answer: titles.length ? `Related notes: ${titles.join("; ")}` : "No matches.", sources: titles });
    }
    if (p === "/app/capture" && req.method === "POST") {
      if (!accessOk(req)) return json({ error: "forbidden" }, 403);
      const b = (await req.json()) as { text: string };
      await storeCapture(env, "web", b.text ?? "");
      return json({ ok: true });
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
