import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, formatApiErrorDetail, getToken, setToken } from "@/lib/api";

const AuthContext = createContext({ user: null, loading: true });

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchMe = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const r = await api.get("/auth/me");
      if (r.data?.success) setUser(r.data.data);
      else { setUser(null); setToken(null); }
    } catch (_e) {
      setUser(null);
      setToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchMe(); }, [fetchMe]);

  const login = useCallback(async (email, password) => {
    try {
      const r = await api.post("/auth/login", { email, password });
      if (r.data?.success) {
        setToken(r.data.data.access_token);
        setUser(r.data.data.user);
        return { ok: true, redirect: r.data.data.redirect_to };
      }
      const err = r.data?.errors?.[0];
      return { ok: false, error: formatApiErrorDetail(err?.message ?? err) };
    } catch (e) {
      return {
        ok: false,
        error: formatApiErrorDetail(
          e.response?.data?.errors?.[0]?.message ?? e.message,
        ),
      };
    }
  }, []);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch (_e) { /* ignore */ }
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh: fetchMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() { return useContext(AuthContext); }
