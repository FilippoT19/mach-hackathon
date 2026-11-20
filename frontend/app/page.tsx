"use client";
import { useEffect, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
type Msg = { role: "user" | "assistant"; content: string; agent?: string };
type Task = { id: string; title: string; status: string; due_at?: string; agent: string };

export default function Home() {
  const [userId, setUserId] = useState<string | null>(null);
  const [convId, setConvId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("userId");
    if (saved) return setUserId(saved);
    fetch(`${API}/users`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Demo citizen" }),
    })
      .then((r) => r.json())
      .then((u) => { localStorage.setItem("userId", u.id); setUserId(u.id); });
  }, []);

  const refresh = async (uid: string) => {
    const d = await fetch(`${API}/users/${uid}/dashboard`).then((r) => r.json());
    setTasks(d.tasks ?? []);
  };
  useEffect(() => { if (userId) refresh(userId); }, [userId]);

  const send = async () => {
    if (!input.trim() || !userId) return;
    const text = input;
    setInput("");
    setMsgs((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const r = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, message: text, conversation_id: convId }),
      }).then((r) => r.json());
      setConvId(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply ?? JSON.stringify(r), agent: r.agent }]);
      refresh(userId);
    } finally { setBusy(false); }
  };

  return (
    <main style={{ display: "grid", gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr)", gap: 16, padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <section style={card}>
        <h2 style={{ marginTop: 0 }}>Assistant</h2>
        <div style={{ minHeight: 360, display: "flex", flexDirection: "column", gap: 8 }}>
          {msgs.map((m, i) => (
            <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "80%", background: m.role === "user" ? "#2563eb" : "#eef0f3", color: m.role === "user" ? "#fff" : "#111", padding: "8px 12px", borderRadius: 12, whiteSpace: "pre-wrap" }}>
              {m.agent && <div style={{ fontSize: 11, opacity: 0.6 }}>{m.agent}</div>}
              {m.content}
            </div>
          ))}
          {busy && <div style={{ opacity: 0.6 }}>thinking…</div>}
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="e.g. I need to renew my ID card and book a blood test" style={{ flex: 1, padding: 10, borderRadius: 8, border: "1px solid #ccc" }} />
          <button onClick={send} disabled={busy} style={{ padding: "10px 16px", borderRadius: 8, border: 0, background: "#2563eb", color: "#fff" }}>Send</button>
        </div>
      </section>
      <aside style={card}>
        <h3 style={{ marginTop: 0 }}>My tasks</h3>
        {tasks.length === 0 && <p style={{ opacity: 0.6 }}>No tasks yet.</p>}
        {tasks.map((t) => (
          <div key={t.id} style={{ borderBottom: "1px solid #eee", padding: "6px 0" }}>
            <b>{t.title}</b>
            <div style={{ fontSize: 12, opacity: 0.7 }}>{t.agent} · {t.status}{t.due_at ? ` · ${t.due_at}` : ""}</div>
          </div>
        ))}
      </aside>
    </main>
  );
}

const card: React.CSSProperties = { background: "#fff", borderRadius: 12, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,.08)" };
