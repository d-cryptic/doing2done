export interface Env {
  DB: D1Database;
  AI: Ai;
  VECTORIZE: VectorizeIndex;
  ASSETS: R2Bucket;
  INGEST_TOKEN?: string;
}

const EMBED_MODEL = "@cf/baai/bge-base-en-v1.5";

async function embed(env: Env, text: string): Promise<number[]> {
  const out: any = await env.AI.run(EMBED_MODEL, { text: [text.slice(0, 2000)] });
  return out.data[0];
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === "/health") {
      return Response.json({ ok: true, service: "doing2done" });
    }

    if (url.pathname === "/ingest" && req.method === "POST") {
      const auth = req.headers.get("authorization") ?? "";
      if (!env.INGEST_TOKEN || auth !== `Bearer ${env.INGEST_TOKEN}`) {
        return Response.json({ error: "unauthorized" }, { status: 401 });
      }
      const notes = (await req.json()) as Array<{
        note_id: string; title: string; body: string; modified: string;
      }>;
      const vectors = [];
      for (const nt of notes) {
        await env.DB.prepare(
          "INSERT OR REPLACE INTO notes(note_id,title,body,modified,updated_at) " +
          "VALUES (?,?,?,?,datetime('now'))"
        ).bind(nt.note_id, nt.title ?? "", nt.body ?? "", nt.modified ?? "").run();
        try {
          const values = await embed(env, `${nt.title}\n${nt.body}`);
          vectors.push({ id: nt.note_id.slice(0, 64), values, metadata: { title: nt.title } });
        } catch (_) { /* embedding optional */ }
      }
      if (vectors.length) await env.VECTORIZE.upsert(vectors);
      return Response.json({ ingested: notes.length, embedded: vectors.length });
    }

    // Semantic recall via Vectorize.
    if (url.pathname === "/ask") {
      const auth = req.headers.get("authorization") ?? "";
      if (!env.INGEST_TOKEN || auth !== `Bearer ${env.INGEST_TOKEN}`) {
        return Response.json({ error: "unauthorized" }, { status: 401 });
      }
      const q = url.searchParams.get("q") ?? "";
      if (!q) return Response.json({ error: "missing q" }, { status: 400 });
      const qv = await embed(env, q);
      const res = await env.VECTORIZE.query(qv, { topK: 8, returnMetadata: true });
      return Response.json({
        query: q,
        hits: res.matches.map((m: any) => ({
          note_id: m.id, title: m.metadata?.title, score: Number(m.score.toFixed(3)),
        })),
      });
    }

    return new Response("doing2done worker", { status: 200 });
  },
};
