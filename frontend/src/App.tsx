import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { AdminPage } from "./pages/Admin";
import { DashboardPage } from "./pages/Dashboard";
import { ItemPage } from "./pages/ItemDetail";
import { LoginPage } from "./pages/Login";
import { SettingsPage } from "./pages/Settings";

function Private() {
  const { user, ready } = useAuth();
  if (!ready) return <p className="p-6 text-muted">Loading…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Private />}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/items/:itemId" element={<ItemPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Route>
    </Routes>
  );
}
