import Link from "next/link";
import { FileText, Gauge, GitCompare, History, Layers, Sprout } from "lucide-react";

const FEATURES = [
  { icon: Layers, title: "Parcel Detection", text: "Automatic delineation of agricultural parcel boundaries inside any study area you draw." },
  { icon: Sprout, title: "Crop Classification", text: "Random Forest classification of Paddy, Banana, Other Vegetation and Non-Agricultural land." },
  { icon: GitCompare, title: "Change Detection", text: "Spot Paddy → Banana conversions, new cultivation and non-crop conversion between seasons." },
  { icon: Gauge, title: "AI Confidence Scoring", text: "Every prediction carries a High / Medium / Low confidence and a plain-language explanation." },
  { icon: History, title: "Historical Analysis", text: "Compare 2024, 2025 and 2026 side by side with area and parcel deltas." },
  { icon: FileText, title: "Report Generation", text: "One-click PDF reports plus CSV and GeoJSON exports for GIS workflows." },
];

export default function Landing() {
  return (
    <div>
      <section className="bg-gradient-to-b from-brand-900 to-slate-950 px-6 py-24 text-center text-white">
        <p className="mb-3 text-sm font-semibold uppercase tracking-widest text-brand-500">Tirunelveli District · Ambasamudram &amp; Cheranmahadevi</p>
        <h1 className="text-5xl font-extrabold tracking-tight sm:text-7xl">AGRIVISION AI</h1>
        <p className="mt-4 text-xl text-brand-50/90 sm:text-2xl">Satellite-Powered Agricultural Intelligence</p>
        <p className="mx-auto mt-6 max-w-2xl text-slate-300">Transforming open satellite imagery into actionable crop intelligence.</p>
        <div className="mt-10 flex flex-wrap justify-center gap-4">
          <Link href="/analysis" className="btn btn-primary !px-8 !py-3 text-base">Launch Analysis</Link>
          <a href="#features" className="btn !px-8 !py-3 border border-white/30 text-base hover:bg-white/10">Learn More</a>
        </div>
      </section>
      <section id="features" className="mx-auto max-w-6xl px-6 py-20">
        <h2 className="mb-10 text-center text-3xl font-bold">Built for agricultural decision-makers</h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <div key={title} className="card">
              <span className="mb-3 inline-flex rounded-lg bg-brand-50 p-2 text-brand-600 dark:bg-brand-900/40"><Icon size={22} /></span>
              <h3 className="mb-1 font-semibold">{title}</h3>
              <p className="text-sm text-slate-600 dark:text-slate-400">{text}</p>
            </div>
          ))}
        </div>
        <p className="mx-auto mt-12 max-w-3xl text-center text-sm text-slate-500">
          This MVP runs on a simulated Sentinel-2 feature layer so it works fully offline. The data layer is isolated, so real Sentinel-2
          NDVI / EVI / NDWI composites can be plugged in without changing the classifier, API or UI.
        </p>
      </section>
    </div>
  );
}
