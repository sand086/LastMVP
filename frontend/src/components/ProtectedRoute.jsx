import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";

export default function ProtectedRoute({ children, allow }) {
  const { user, loading } = useAuth();
  const loc = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-mye-app">
        <div className="text-mye-ink-muted text-sm font-mono" data-testid="auth-loading">
          Cargando sesión…
        </div>
      </div>
    );
  }

  if (!user) {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (Array.isArray(allow) && allow.length > 0 && !allow.includes(user.role)) {
    return <Navigate to="/default" replace />;
  }

  return children;
}
