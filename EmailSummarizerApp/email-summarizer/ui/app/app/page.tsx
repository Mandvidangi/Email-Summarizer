"use client";
import { useEffect, useState } from "react";

type Thread = { thread_id: string; subject: string; from?: string; date?: string; };

export default function AppPage() {
  const API = process.env.NEXT_PUBLIC_API_BASE!;
  const [token, setToken] = useState<string | null>(null);
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<any | null>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    const t = url.searchParams.get("token") || localStorage.getItem("app_token");
    if (t) {
      localStorage.setItem("app_token", t);
      setToken(t);
      fetch(`${API}/v1/me/threads`, { headers: { Authorization: `Bearer ${t}` } })
        .then(r => r.json())
        .then(d => setThreads(d.threads || []));
    }
  }, [API]);

  const summarize = async (thread_id: string) => {
    if (!token) return;
    setLoading(true);
    setSummary(null);
    const res = await fetch(`${API}/v1/me/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ thread_id }),
    });
    const data = await res.json();
    setSummary(data.summary);
    setLoading(false);
  };

  return (
    <main className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">Your Recent Emails</h1>
      {!token && <p>Missing session—please go back and Sign in with Google.</p>}

      <div className="grid gap-3">
        {threads.map(t => (
          <div key={t.thread_id} className="rounded-xl border p-4 flex items-center justify-between">
            <div className="min-w-0">
              <div className="font-medium truncate">{t.subject || "(no subject)"}</div>
              <div className="text-sm text-gray-500 truncate">{t.from} • {t.date}</div>
            </div>
            <button
              onClick={() => summarize(t.thread_id)}
              className="px-3 py-2 rounded-lg bg-black text-white"
            >
              Summarize
            </button>
          </div>
        ))}
      </div>

      {loading && <div className="animate-pulse text-gray-600">Summarizing…</div>}

      {summary && (
        <div className="rounded-xl border p-4 space-y-2">
          <div className="text-lg font-semibold">{summary.subject}</div>
          <div className="text-sm text-gray-500">
            Sentiment: {summary.sentiment} • Confidence: {summary.confidence}
          </div>
          <div>
            <div className="font-medium mt-2">Key Points</div>
            <ul className="list-disc ml-6">
              {summary.key_points?.map((k: string, i: number) => <li key={i}>{k}</li>)}
            </ul>
          </div>
          {!!summary.actions?.length && (
            <div>
              <div className="font-medium mt-2">Actions</div>
              <ul className="list-disc ml-6">
                {summary.actions.map((a: any, i: number) => (
                  <li key={i}>
                    {a.who}: {a.what} {a.due ? `(due ${a.due})` : ""} [{a.priority}]
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
