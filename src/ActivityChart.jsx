import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export default function ActivityChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%">
    <AreaChart data={data} margin={{ top: 4, right: 5, bottom: 0, left: -22 }}>
      <defs><linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#a9df60" stopOpacity={0.22} /><stop offset="100%" stopColor="#a9df60" stopOpacity={0} /></linearGradient></defs>
      <CartesianGrid stroke="#29362d" strokeDasharray="3 5" vertical={false} />
      <XAxis dataKey="date" tick={{ fill: '#849187', fontSize: 9 }} axisLine={false} tickLine={false} />
      <YAxis allowDecimals={false} tick={{ fill: '#849187', fontSize: 9 }} axisLine={false} tickLine={false} />
      <Tooltip contentStyle={{ background: '#1b251e', border: '1px solid #38453b', borderRadius: 8, color: '#e5eee6', fontSize: 10 }} />
      <Area type="monotone" dataKey="count" stroke="#a9df60" strokeWidth={2} fill="url(#activityFill)" />
    </AreaChart>
  </ResponsiveContainer>
}
