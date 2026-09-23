import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
type Rail = { id: number; store_id: number; label: string; length_cm: number };
type Seg = { order_id: number; ticket_code: string; garment_name: string; start_cm: number; end_cm: number };
type Occ = { rail_id: number; label: string; length_cm: number; segments: Seg[] };
export default function OccupancyPage() {
  const [rails, setRails] = useState<Rail[]>([]);
  const [maps, setMaps] = useState<Occ[]>([]);
  const [targets, setTargets] = useState<Record<number, number>>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");

  const reload = useCallback(() => {
    return api<Rail[]>("/rails").then(async rs => {
      setRails(rs);
      const all = await Promise.all(rs.map(r => api<Occ>(`/occupancy/${r.id}`)));
      setMaps(all);
    });
  }, []);
  useEffect(() => { reload(); }, [reload]);

  async function move(orderId: number) {
    const targetRailId = targets[orderId];
    if (!targetRailId) { setErr("请先选择目标挂杆"); return; }
    setBusy(orderId); setMsg(""); setErr("");
    try {
      await api("/move", { method: "POST", body: JSON.stringify({ order_id: orderId, target_rail_id: targetRailId }) });
      setMsg("移杆成功");
      await reload();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(null); }
  }

  return (<>
    <h2>占位图（横向尺线）</h2>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    {maps.map(m => {
      const rail = rails.find(r => r.id === m.rail_id);
      const sameStore = rails.filter(r => rail && r.store_id === rail.store_id && r.id !== m.rail_id);
      return (
        <div className="ruler-wrap" key={m.rail_id}>
          <div className="ruler-label"><span>{m.label}</span><span className="mono">0 — {m.length_cm} cm</span></div>
          <div className="ruler">
            {m.segments.map(s => (
              <div key={s.order_id} className="seg" style={{ left: `${(s.start_cm / m.length_cm) * 100}%`, width: `${((s.end_cm - s.start_cm) / m.length_cm) * 100}%` }}
                title={`${s.ticket_code} ${s.start_cm}-${s.end_cm}cm`}>
                {s.garment_name}
              </div>
            ))}
          </div>
          {m.segments.length > 0 && (
            <div className="move-row">
              {m.segments.map(s => (
                <div className="move-item" key={s.order_id}>
                  <span className="mono">{s.ticket_code}</span>
                  <span>{s.garment_name} · {s.start_cm}-{s.end_cm}cm</span>
                  {sameStore.length > 0
                    ? <><select value={targets[s.order_id] ?? ""} onChange={e => setTargets(t => ({ ...t, [s.order_id]: Number(e.target.value) }))}>
                        <option value="" disabled>目标挂杆</option>
                        {sameStore.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
                      </select>
                      <button disabled={busy === s.order_id} onClick={() => move(s.order_id)}>
                        {busy === s.order_id ? "移杆中…" : "移杆"}
                      </button></>
                    : <span className="move-na">无同店目标杆</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    })}
    {!rails.length && <p>暂无挂杆</p>}
  </>);
}
