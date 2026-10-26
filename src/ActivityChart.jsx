import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

export default function ActivityChart({ data }) {
  return <ResponsiveContainer width="100%" height="100%">
    <AreaChart data={data} margin={{ top: 4, right: 5, bottom: 0, left: -22 }}>
      <defs><linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" stopOpacity={0.2} /><stop offset="100%" stopColor="var(--accent)" stopOpacity={0} /></linearGradient></defs>
      <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" vertical={false} />
      <XAxis dataKey="date" tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} axisLine={false} tickLine={false} />
      <YAxis allowDecimals={false} tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} axisLine={false} tickLine={false} />
      <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text)', fontSize: 11, boxShadow: 'var(--shadow)' }} />
      <Area type="monotone" dataKey="count" stroke="var(--accent)" strokeWidth={2} fill="url(#activityFill)" />
    </AreaChart>
  </ResponsiveContainer>
}
