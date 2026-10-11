"use client";
import { Loader2, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import * as api from "@/lib/api";
import { CHANGE_COLORS, CROPS, CROP_COLORS, ChangeResult, HistoryResult, LEVEL_COLORS, ParcelDetail, Stats, YEARS } from "@/lib/types";

export const Spinner = ({ text }: { text?: string }) => (
  <div className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="animate-spin" size={16} />{text || "Loading..."}</div>
);

const Metric = ({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) => (
  <div className="card !p-3">
    <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
      {color && <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />}{label}
    </div>
    <div className="mt-1 text-xl font-bold">{value}</div>
    {sub && <div className="text-xs text-slate-500">{sub}</div>}
  </div>
);

export function StatsGrid({ s }: { s: Stats }) {
  const ha = (v: number) => `${v.toLocaleString(undefined, { maximumFractionDigits: 1 })} ha`;
  return (
    <div className="grid grid-cols-2 gap-2">
      <Metric label="Total area" value={ha(s.total_area_ha)} sub={`${s.total_parcels} parcels`} />
      <Metric label="Agricultural" value={ha(s.agricultural_area_ha)} sub="Paddy + Banana" />
      <Metric label="Paddy" value={ha(s.crop_area_ha["Paddy"])} sub={`${s.crop_pct["Paddy"]}%`} color={CROP_COLORS.Paddy} />
      <Metric label="Banana" value={ha(s.crop_area_ha["Banana"])} sub={`${s.crop_pct["Banana"]}%`} color={CROP_COLORS.Banana} />
      <Metric label="Other vegetation" value={ha(s.crop_area_ha["Other Vegetation"])} sub={`${s.crop_pct["Other Vegetation"]}%`} color={CROP_COLORS["Other Vegetation"]} />
      <Metric label="Avg confidence" value={`${(s.avg_confidence * 100).toFixed(1)}%`} sub={`High ${s.confidence_levels.High} · Med ${s.confidence_levels.Medium} · Low ${s.confidence_levels.Low}`} />
    </div>
  );
}

export function ParcelCard({ p, onClose }: { p: ParcelDetail; onClose: () => void }) {
  return (
    <div className="card space-y-2 border-brand-600 !p-3">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase text-slate-500">Parcel</div>
          <div className="font-bold">{p.parcel_id} <span className="text-xs font-normal text-slate-500">· {p.area_ha} ha · {p.year}</span></div>
        </div>
        <button onClick={onClose} className="text-xs text-slate-500 hover:underline">close</button>
      </div>
      <div className="flex items-center gap-2">
        <span className="rounded-full px-3 py-0.5 text-sm font-semibold text-slate-900" style={{ background: CROP_COLORS[p.crop_type] }}>{p.crop_type}</span>
        <span className="rounded-full px-2 py-0.5 text-xs font-semibold text-white" style={{ background: LEVEL_COLORS[p.confidence_level] }}>{p.confidence_level}</span>
        <span className="text-sm">{(p.confidence * 100).toFixed(0)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-slate-200 dark:bg-slate-700">
        <div className="h-full" style={{ width: `${p.confidence * 100}%`, background: LEVEL_COLORS[p.confidence_level] }} />
      </div>
      <div>
        <div className="label !mb-0.5">Why classified?</div>
        <ul className="list-disc space-y-0.5 pl-4 text-xs">{p.explanation.map((e, i) => <li key={i}>{e}</li>)}</ul>
      </div>
      <div>
        <div className="label !mb-0.5">History</div>
        <div className="flex flex-wrap gap-1.5 text-xs">
          {p.history.map((h) => (
            <span key={h.year} className="rounded border border-slate-300 px-1.5 py-0.5 dark:border-slate-700">
              {h.year}: <b>{h.crop_type}</b> ({(h.confidence * 100).toFixed(0)}%)
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

const YearSelect = ({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) => (
  <div className="flex-1">
    <label className="label">{label}</label>
    <select className="input" value={value} onChange={(e) => onChange(+e.target.value)}>{YEARS.map((y) => <option key={y}>{y}</option>)}</select>
  </div>
);

export function ComparePanel(props: {
  job: string; a: number; b: number; setA: (n: number) => void; setB: (n: number) => void;
  mode: "crops" | "changes"; setMode: (m: "crops" | "changes") => void; onChanges: (c: ChangeResult | null) => void; onSelect: (id: string) => void;
}) {
  const { job, a, b } = props;
  const [hist, setHist] = useState<HistoryResult | null>(null);
  const [ch, setCh] = useState<ChangeResult | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (a === b) { setErr("Choose two different periods to compare."); setHist(null); setCh(null); props.onChanges(null); return; }
    setErr("");
    let live = true;
    Promise.all([api.getHistory(job, a, b), api.getChanges(job, a, b)])
      .then(([h, c]) => { if (live) { setHist(h); setCh(c); props.onChanges(c.geojson); } })
      .catch((e) => live && setErr(e.message));
    return () => { live = false; };
  }, [job, a, b]); // eslint-disable-line
  return (
    <div className="space-y-3">
      <div className="flex gap-2"><YearSelect label="Period A" value={a} onChange={props.setA} /><YearSelect label="Period B" value={b} onChange={props.setB} /></div>
      {err && <div className="text-sm text-red-500">{err}</div>}
      {!err && !hist && <Spinner />}
      {hist && ch && (
        <>
          <div className="card !p-3">
            <div className="label">Area change by class (ha)</div>
            <table className="w-full text-xs">
              <thead><tr className="text-left text-slate-500"><th>Class</th><th>{a}</th><th>{b}</th><th>Δ</th></tr></thead>
              <tbody>
                {CROPS.map((c) => {
                  const d = hist.delta[c].area_ha;
                  return (
                    <tr key={c} className="border-t border-slate-200 dark:border-slate-800">
                      <td className="py-1"><span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: CROP_COLORS[c] }} />{c}</td>
                      <td>{hist.period_a.stats.crop_area_ha[c]}</td><td>{hist.period_b.stats.crop_area_ha[c]}</td>
                      <td className={d >= 0 ? "text-green-600" : "text-red-500"}>{d >= 0 ? "+" : ""}{d}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="mt-1 text-xs text-slate-500">Parcels: {hist.period_a.stats.total_parcels} → {hist.period_b.stats.total_parcels}</div>
          </div>
          <div className="card !p-3">
            <div className="mb-1 flex items-center justify-between">
              <div className="label !mb-0">Change detection · {ch.total_changed} of {ch.total_parcels} parcels</div>
            </div>
            {Object.entries(ch.summary).map(([k, v]) => (
              <div key={k} className="flex items-center justify-between py-0.5 text-xs">
                <span><span className="mr-1 inline-block h-2.5 w-2.5 rounded" style={{ background: CHANGE_COLORS[k] }} />{k}</span>
                <span>{v.count} parcels · {v.area_ha} ha</span>
              </div>
            ))}
            <button className="btn btn-primary mt-2 w-full !py-1.5" onClick={() => props.setMode(props.mode === "changes" ? "crops" : "changes")}>
              {props.mode === "changes" ? "Show crop map" : "Visualize changes on map"}
            </button>
          </div>
          <div className="card max-h-56 overflow-auto !p-3">
            <div className="label">Changed parcels</div>
            {ch.changes.slice(0, 150).map((c) => (
              <button key={c.parcel_id} onClick={() => props.onSelect(c.parcel_id)} className="block w-full border-t border-slate-200 py-1 text-left text-xs hover:bg-slate-100 dark:border-slate-800 dark:hover:bg-slate-800">
                <b>{c.parcel_id}</b> · {a}: {c.from_crop} → {b}: {c.to_crop}
              </button>
            ))}
            {ch.changes.length === 0 && <div className="text-xs text-slate-500">No changes between these periods.</div>}
          </div>
        </>
      )}
    </div>
  );
}

export function ChatPanel({ job, a, b, onHighlight }: { job: string; a: number; b: number; onHighlight: (ids: string[]) => void }) {
  const [msgs, setMsgs] = useState<{ who: "me" | "ai"; text: string }[]>([
    { who: "ai", text: "Ask me about this analysis - crop areas, confidence, or parcels that changed between periods." },
  ]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  const send = async (q: string) => {
    if (!q.trim() || busy) return;
    setMsgs((m) => [...m, { who: "me", text: q }]);
    setText(""); setBusy(true);
    try {
      const r = await api.chat(job, q, a, b);
      setMsgs((m) => [...m, { who: "ai", text: r.answer }]);
      onHighlight(r.highlight_parcels);
    } catch (e: any) {
      setMsgs((m) => [...m, { who: "ai", text: "Error: " + e.message }]);
    } finally { setBusy(false); }
  };
  const examples = ["Which crop occupies the largest area?", "Show parcels where Paddy changed to Banana", "What is the average confidence score?", "Show low confidence parcels"];
  return (
    <div className="flex h-full min-h-[360px] flex-col">
      <div className="flex-1 space-y-2 overflow-auto">
        {msgs.map((m, i) => (
          <div key={i} className={`max-w-[92%] rounded-lg px-3 py-2 text-sm ${m.who === "me" ? "ml-auto bg-brand-600 text-white" : "bg-slate-100 dark:bg-slate-800"}`}>{m.text}</div>
        ))}
        {busy && <Spinner text="Querying database..." />}
        <div ref={end} />
      </div>
      <div className="my-2 flex flex-wrap gap-1.5">
        {examples.map((e) => <button key={e} onClick={() => send(e)} className="rounded-full border border-slate-300 px-2 py-0.5 text-[11px] hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800">{e}</button>)}
        <button onClick={() => onHighlight([])} className="rounded-full border border-slate-300 px-2 py-0.5 text-[11px] dark:border-slate-700">Clear highlights</button>
      </div>
      <div className="flex gap-2">
        <input className="input" value={text} maxLength={300} placeholder="Ask about your results..." onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send(text)} />
        <button className="btn btn-primary !px-3" onClick={() => send(text)} disabled={busy} aria-label="Send"><Send size={16} /></button>
      </div>
    </div>
  );
}
