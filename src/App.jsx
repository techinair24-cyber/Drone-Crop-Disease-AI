import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './layout.jsx'
import {
  AnalysisPage,
  HistoryPage,
  MapPage,
  MonitorPage,
  OverviewPage,
  RecommendationsPage,
  SettingsPage,
} from './pages.jsx'
import './App.css'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="monitor" element={<MonitorPage />} />
          <Route path="analysis" element={<AnalysisPage />} />
          <Route path="map" element={<MapPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
