"use client";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CROPS, CROP_COLORS, LEVEL_COLORS, Stats } from "@/lib/types";

const Box = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div className="card !p-3">
    <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
    <div className="h-44">{children}</div>
  </div>
);

export default function Charts({ stats }: { stats: Stats }) {
  const crop = CROPS.map((c) => ({ name: c, value: stats.crop_area_ha[c] }));
  const conf = ["High", "Medium", "Low"].map((l) => ({ name: l, count: stats.confidence_levels[l] }));
  return (
    <div className="space-y-3">
      <Box title="Crop distribution (ha)">
        <ResponsiveContainer>
          <PieChart>
            <Pie data={crop} dataKey="value" nameKey="name" innerRadius={34} outerRadius={64} paddingAngle={2}>
              {crop.map((d) => <Cell key={d.name} fill={CROP_COLORS[d.name as keyof typeof CROP_COLORS]} />)}
            </Pie>
            <Tooltip /><Legend wrapperStyle={{ fontSize: 11 }} />
          </PieChart>
        </ResponsiveContainer>
      </Box>
      <Box title="Parcel size distribution (parcels)">
        <ResponsiveContainer>
          <BarChart data={stats.size_distribution}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="bucket" fontSize={11} /><YAxis fontSize={11} />
            <Tooltip /><Bar dataKey="count" fill="#16a34a" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Box>
      <Box title="Confidence distribution (parcels)">
        <ResponsiveContainer>
          <BarChart data={conf}>
            <CartesianGrid strokeDasharray="3 3" opacity={0.3} /><XAxis dataKey="name" fontSize={11} /><YAxis fontSize={11} />
            <Tooltip />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>{conf.map((d) => <Cell key={d.name} fill={LEVEL_COLORS[d.name]} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      </Box>
    </div>
  );
}
