// Надёжный планировщик GitHub Actions: Cloudflare cron -> workflow_dispatch.
// GitHub schedule на free-репозиториях сильно опаздывает/пропускает слоты,
// поэтому точные слоты (4 поста Fediverse, рост Mastodon, Buffer, Tumblr)
// запускаются отсюда.

const DEDUPE_TTL = 600; // секунд

async function dispatch(env, workflow, ref) {
  const repo = env.REPO;
  if (!repo || !env.GITHUB_TOKEN || !workflow) return { workflow, ok: false, error: "not configured" };
  const response = await fetch(
    `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "cf-github-cron",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: ref || "main" }),
    }
  );
  return { workflow, ok: response.status === 204, status: response.status };
}

export default {
  async scheduled(event, env, ctx) {
    const at = new Date(event.scheduledTime);
    const minute = at.getUTCMinutes();
    const hour = at.getUTCHours();
    const jobs = [];
    if (minute === 17 && [10, 14, 18, 22].includes(hour)) jobs.push("fediverse-mix.yml");
    if (minute === 17 && hour === 16) jobs.push("mastodon-growth.yml");
    if (minute === 10 && hour === 3) jobs.push("buffer-queue.yml");
    if (minute === 0 && hour % 5 === 0) jobs.push("tumblr-digest.yml");
    for (const workflow of jobs) {
      const key = `run:${at.toISOString().slice(0, 16)}:${workflow}`;
      if (env.CRON_KV) {
        const seen = await env.CRON_KV.get(key);
        if (seen) continue;
        await env.CRON_KV.put(key, "1", { expirationTtl: DEDUPE_TTL });
      }
      const result = await dispatch(env, workflow, env.REF);
      console.log("dispatch", JSON.stringify(result));
    }
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    const token = request.headers.get("x-token") || url.searchParams.get("token") || "";
    if (url.pathname === "/trigger") {
      if (token !== env.ADMIN_TOKEN) return Response.json({ ok: false, error: "forbidden" }, { status: 403 });
      const workflow = url.searchParams.get("workflow") || "";
      if (!workflow) return Response.json({ ok: false, error: "workflow required" }, { status: 400 });
      const result = await dispatch(env, workflow, url.searchParams.get("ref") || env.REF);
      return Response.json({ ok: result.ok, result });
    }
    return Response.json({
      ok: true,
      service: "github-cron",
      repo: env.REPO || "",
      slots: {
        "fediverse-mix.yml": "10:17, 14:17, 18:17, 22:17 UTC",
        "mastodon-growth.yml": "16:17 UTC",
        "buffer-queue.yml": "03:10 UTC",
        "tumblr-digest.yml": "every 5 hours (:00)",
      },
    });
  },
};
