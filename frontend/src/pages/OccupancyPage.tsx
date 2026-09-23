import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
type R = { id: number; store_id: number; label: string; length_cm: number };
type Seg = { order_id: number; ticket_code: string; garment_name: string; start_cm: number; end_cm: number };
type Occ = { rail_id: number; label: string; length_cm: number; segments: Seg[] };
type Moving = { rail_id: number; seg: Seg };

export default function OccupancyPage() {
  const [rails, setRails] = useState<R[]>([]);
  const [maps, setMaps] = useState<Occ[]>([]);
  const [moving, setMoving] = useState<Moving | null>(null);
  const [targetRailId, setTargetRailId] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const reload = useCallback(async () => {
    const rs = await api<R[]>("/rails");
    setRails(rs);
    const all = await Promise.all(rs.map(r => api<Occ>(`/occupancy/${r.id}`)));
    setMaps(all);
  }, []);

  useEffect(() => { reload(); }, [reload]);

  function startMove(rail_id: number, seg: Seg) {
    setMsg(""); setErr("");
    setMoving({ rail_id, seg });
    setTargetRailId("");
  }

  async function confirmMove() {
    if (!moving || targetRailId === "") return;
    setBusy(true); setMsg(""); setErr("");
    try {
      await api("/move", {
        method: "POST",
        body: JSON.stringify({ order_id: moving.seg.order_id, target_rail_id: targetRailId }),
      });
      setMsg(`${moving.seg.ticket_code} 已移至目标挂杆`);
      setMoving(null);
      await reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (<>
    <h2>占位图（横向尺线）</h2>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    {maps.map(m => {
      const rail = rails.find(r => r.id === m.rail_id);
      // 仅同店其他杆可作为移杆目标，跨店杆不出现
      const targets = rails.filter(r => rail && r.store_id === rail.store_id && r.id !== m.rail_id);
      return (
        <div className="ruler-wrap" key={m.rail_id}>
          <div className="ruler-label"><span>{m.label}</span><span className="mono">0 — {m.length_cm} cm</span></div>
          <div className="ruler">
            {m.segments.map((s, i) => (
              <div key={i} className="seg" style={{ left: `${(s.start_cm / m.length_cm) * 100}%`, width: `${((s.end_cm - s.start_cm) / m.length_cm) * 100}%` }}
                title={`${s.ticket_code} ${s.start_cm}-${s.end_cm}cm`}>
                <span className="seg-name">{s.garment_name}</span>
                <button type="button" className="seg-move" title={`移杆 ${s.ticket_code}`}
                  onClick={() => startMove(m.rail_id, s)}>移</button>
              </div>
            ))}
          </div>
          {moving?.rail_id === m.rail_id && (
            <div className="toolbar move-bar">
              <span>把 <span className="mono">{moving.seg.ticket_code}</span>（{moving.seg.garment_name}）移到</span>
              <select value={targetRailId} onChange={e => setTargetRailId(Number(e.target.value))}>
                <option value="" disabled>选择目标挂杆</option>
                {targets.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
              <button type="button" disabled={busy || targetRailId === "" || targets.length === 0} onClick={confirmMove}>
                {busy ? "移杆中…" : "确认移杆"}
              </button>
              <button type="button" className="btn-ghost" disabled={busy} onClick={() => setMoving(null)}>取消</button>
              {targets.length === 0 && <span className="err">同店无其他挂杆</span>}
            </div>
          )}
        </div>
      );
    })}
    {!rails.length && <p>暂无挂杆</p>}
  </>);
}
