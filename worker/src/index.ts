export interface Env {
  DB: D1Database;
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

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const p = url.pathname;

    if (p === "/health") return json({ ok: true, service: "doing2done" });

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
      return json({ id });
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
        await storeCapture(env, "whatsapp", body);
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
