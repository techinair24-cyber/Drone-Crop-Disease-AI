import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3, Camera, ClipboardList, Crosshair, Leaf, MapPinned, Menu,
  Moon, Settings, Sprout, Sun, X,
} from 'lucide-react'
import { api } from './api.js'

function getStoredTheme() {
  try {
    const stored = localStorage.getItem('theme')
    return stored === 'light' || stored === 'dark' ? stored : 'light'
  } catch {
    return 'light'
  }
}

function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

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
  const [health, setHealth] = useState()
  const [themePreference, setThemePreference] = useState(getStoredTheme)
  const [systemTheme, setSystemTheme] = useState(getSystemTheme)
  const location = useLocation()
  const theme = themePreference || systemTheme
  const refreshMs = Math.max(5000, Number(localStorage.getItem('refreshInterval') || 30000))

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const updateSystemTheme = (event) => setSystemTheme(event.matches ? 'dark' : 'light')
    media.addEventListener('change', updateSystemTheme)
    return () => media.removeEventListener('change', updateSystemTheme)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.style.colorScheme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute(
      'content',
      theme === 'dark' ? '#0f172a' : '#f7f9f6',
    )
  }, [theme])

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
          <span className="brand-name">TECH IN AIR<span className="brand-sub">DRONE CROP DISEASE AI</span></span>
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
      </aside>
      {sidebarOpen && <button className="sidebar-backdrop" type="button" aria-label="Close navigation menu" onClick={() => setSidebarOpen(false)} />}
      <div className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" aria-label={sidebarOpen ? 'Close menu' : 'Open menu'} onClick={() => setSidebarOpen((open) => !open)}>
              {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <div><div className="breadcrumb">Field intelligence / Workspace</div><div className="page-heading">{titles[location.pathname] || 'Overview'}</div></div>
          </div>
          <div className="topbar-actions">
            <div className="connection-pill" title={health ? 'Backend reachable' : health === null ? 'Backend unavailable' : 'Checking backend'}>
              <span className={`status-dot ${health ? 'online' : health === null ? 'offline' : ''}`} />{health ? 'Backend online' : health === null ? 'Backend offline' : 'Checking backend'}
            </div>
            <button
              className="theme-toggle"
              type="button"
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
              onClick={() => {
                const nextTheme = theme === 'dark' ? 'light' : 'dark'
                localStorage.setItem('theme', nextTheme)
                setThemePreference(nextTheme)
              }}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
          </div>
        </header>
        <main className="content"><Outlet /></main>
      </div>
    </div>
  )
}
