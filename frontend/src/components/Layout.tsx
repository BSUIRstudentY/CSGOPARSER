import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../auth";

const links = [
  { to: "/", label: "Маркет" },
  { to: "/settings", label: "Настройки" },
  { to: "/admin", label: "Админ" },
];

export function Layout() {
  const { user, logout } = useAuth();
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-panel">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <div>
              <div className="text-xs uppercase tracking-[0.2em] text-gold">CS2</div>
              <div className="text-sm font-medium">Trading Bot</div>
            </div>
            <nav className="flex gap-1 text-sm">
              {links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.to === "/"}
                  className={({ isActive }) =>
                    `rounded px-3 py-1.5 ${isActive ? "bg-ink text-paper" : "text-muted hover:text-paper"}`
                  }
                >
                  {link.label}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted">
            <span className="hidden sm:inline">{user?.email}</span>
            <button
              type="button"
              onClick={logout}
              className="rounded border border-line px-3 py-1 text-paper hover:border-gold"
            >
              Выйти
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
