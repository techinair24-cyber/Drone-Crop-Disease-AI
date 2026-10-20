import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3, Bell, Camera, ChevronDown, ClipboardList, Crosshair, Leaf,
  MapPinned, Menu, Settings, Sprout, X,
} from 'lucide-react'
import { api } from './api.js'

const links = [
  { to: '/', label: 'Overview', icon: BarChart3, end: true },
  { to: '/monitor', label: 'Live monitoring', icon: Camera },
  { to: '/analysis', label: 'AI analysis', icon: Crosshair },
  { to: '/map', label: 'Disease map', icon: MapPinned },
  { to: '/history', label: 'Detection history', icon: ClipboardList },
  { to: '/recommendations', label: 'Recommendations', icon: Sprout },
]
const titles = {
  '/': 'Overview', '/monitor': 'Live monitoring', '/analysis': 'AI disease analysis',
  '/map': 'Disease geolocation', '/history': 'Detection history',
  '/recommendations': 'Recommendations', '/settings': 'Settings',
}

export function AppShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [health, setHealth] = useState(null)
  const location = useLocation()
  const refreshMs = Math.max(5000, Number(localStorage.getItem('refreshInterval') || 30000))

  useEffect(() => {
    let active = true
    const check = () => api.health().then((data) => {
      if (active) setHealth(data)
    }).catch(() => {
      if (active) setHealth(null)
    })
    check()
    const timer = window.setInterval(check, refreshMs)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [refreshMs])

  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <NavLink className="brand" to="/">
          <span className="brand-mark"><Leaf size={22} /></span>
          <span className="brand-name">DroneCrop AI<span className="brand-sub">FIELD INTELLIGENCE</span></span>
        </NavLink>
        <div className="nav-label">Workspace</div>
        <nav className="nav-list" aria-label="Main navigation">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`} to={to} end={end} onClick={() => setSidebarOpen(false)}>
              <Icon size={16} strokeWidth={1.8} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="nav-label">System</div>
        <nav className="nav-list">
          <NavLink className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`} to="/settings" onClick={() => setSidebarOpen(false)}>
            <Settings size={16} strokeWidth={1.8} /><span>Settings</span>
          </NavLink>
        </nav>
        <div className="sidebar-bottom">
          <div className="flight-card">
            <div className="flight-card-title">Field unit · APM 2.8</div>
            <div className="flight-card-row"><span>Telemetry</span><strong>Unavailable</strong></div>
            <div className="flight-card-row"><span>GPS fix</span><strong>Unavailable</strong></div>
          </div>
          <div className="sidebar-footer">Hardware integrations are pending.<br />No flight commands are enabled.</div>
        </div>
      </aside>
      <div className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" aria-label={sidebarOpen ? 'Close menu' : 'Open menu'} onClick={() => setSidebarOpen((open) => !open)}>
              {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div><div className="breadcrumb">Field intelligence / Workspace</div><div className="page-heading">{titles[location.pathname] || 'Overview'}</div></div>
          </div>
          <div className="topbar-actions">
            <div className="connection-pill" title={health ? 'Backend reachable' : 'Backend unavailable'}>
              <span className={`status-dot ${health ? 'online' : 'offline'}`} />{health ? 'Backend online' : 'Backend offline'}
            </div>
            <button className="mobile-menu" aria-label="Notifications"><Bell size={16} /></button>
            <div className="avatar" title="DroneCrop workspace">DC</div>
            <ChevronDown size={14} color="#829087" />
          </div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  )
}
