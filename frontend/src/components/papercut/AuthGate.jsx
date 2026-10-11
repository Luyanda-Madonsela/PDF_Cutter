import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Scissors, Loader2 } from "lucide-react";
import { getMe, exchangeSession, logout } from "@/lib/api";
import { AUTH } from "@/constants/testIds";

const AuthCtx = createContext(null);
export const useAuth = () => useContext(AuthCtx);

const Splash = () => (
  <div data-testid={AUTH.loading} className="min-h-screen grid place-items-center bg-[var(--pc-bg)] text-[var(--pc-muted)]">
    <Loader2 className="h-6 w-6 animate-spin" />
  </div>
);

const signIn = () => {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const redirectUrl = window.location.origin + "/";
  window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
};

const LoginScreen = () => (
  <div data-testid={AUTH.loginScreen} className="min-h-screen bg-[var(--pc-bg)] text-[var(--pc-text)] font-body pc-grid-bg flex items-center">
    <div className="max-w-7xl w-full mx-auto px-6 lg:px-8 pc-rise">
      <div className="h-12 w-12 rounded-md bg-[var(--pc-amber)] text-[#0B0F19] grid place-items-center mb-10">
        <Scissors className="h-6 w-6" strokeWidth={2.5} />
      </div>
      <h1 className="font-heading text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight leading-[1.05]">
        Every question,<br /><span className="text-[var(--pc-amber)]">cut clean.</span>
      </h1>
      <p className="mt-6 max-w-md text-sm sm:text-base text-[var(--pc-text2)]">
        PaperCut is a private workspace. Sign in with your Google account to open the shared past paper library.
      </p>
      <button data-testid={AUTH.googleButton} onClick={signIn}
        className="mt-10 inline-flex items-center gap-3 px-6 py-3 rounded-full bg-[var(--pc-amber)] text-[#0B0F19] font-semibold transition-transform duration-150 hover:-translate-y-0.5 active:translate-y-0">
        <svg viewBox="0 0 48 48" className="h-5 w-5" aria-hidden="true">
          <path fill="#0B0F19" d="M44.5 20H24v8.5h11.8C34.7 33.9 30.1 37 24 37c-7.2 0-13-5.8-13-13s5.8-13 13-13c3.1 0 5.9 1.1 8.1 2.9l6.4-6.4C34.6 4.1 29.6 2 24 2 11.8 2 2 11.8 2 24s9.8 22 22 22c11 0 21-8 21-22 0-1.3-.2-2.7-.5-4z" />
        </svg>
        Sign in with Google
      </button>
    </div>
  </div>
);

const AuthCallback = ({ onUser }) => {
  const done = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const sid = new URLSearchParams(location.hash.slice(1)).get("session_id");
    exchangeSession(sid)
      .then((u) => onUser(u))
      .catch(() => onUser(false))
      .finally(() => navigate("/", { replace: true }));
  }, [location.hash, navigate, onUser]);
  return <Splash />;
};

export const AuthGate = ({ children }) => {
  const location = useLocation();
  const [user, setUser] = useState(null);
  const inCallback = location.hash?.includes("session_id=");

  useEffect(() => {
    if (inCallback || user) return;
    getMe().then(setUser).catch(() => setUser(false));
  }, [inCallback, user]);

  if (inCallback) return <AuthCallback onUser={setUser} />;
  if (user === null) return <Splash />;
  if (!user) return <LoginScreen />;
  const signOut = () => logout().finally(() => setUser(false));
  return <AuthCtx.Provider value={{ user, signOut }}>{children}</AuthCtx.Provider>;
};
