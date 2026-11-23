// Надёжный планировщик GitHub Actions: Cloudflare cron -> workflow_dispatch.
// GitHub schedule на free-репозиториях сильно опаздывает/пропускает слоты,
// поэтому точные слоты (4 поста Fediverse, рост Mastodon, Buffer, Tumblr)
// запускаются отсюда.

const DEDUPE_TTL = 600; // секунд

async function dispatch(env, workflow, ref, inputs) {
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
      body: JSON.stringify({ ref: ref || "main", inputs: inputs || {} }),
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
    if (minute === 5 && hour === 9) jobs.push({ workflow: "growth-funnel.yml", inputs: { execute: true } });
    if (minute === 30 && hour === 9) jobs.push({ workflow: "travel-report.yml", inputs: {} });
    for (const job of jobs) {
      const workflow = job.workflow;
      const key = `run:${at.toISOString().slice(0, 16)}:${workflow}`;
      if (env.CRON_KV) {
        const seen = await env.CRON_KV.get(key);
        if (seen) continue;
        await env.CRON_KV.put(key, "1", { expirationTtl: DEDUPE_TTL });
      }
      const result = await dispatch(env, workflow, env.REF, job.inputs);
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
      const result = await dispatch(env, workflow, url.searchParams.get("ref") || env.REF, {});
      return Response.json({ ok: result.ok, result });
    }
    return Response.json({
      ok: true,
      service: "github-cron",
      repo: env.REPO || "",
      slots: {
        "growth-funnel.yml": "09:05 UTC daily",
        "travel-report.yml": "09:30 UTC daily",
      },
    });
  },
};
