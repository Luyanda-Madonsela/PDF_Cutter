import { LogOut } from "lucide-react";
import { useAuth } from "./AuthGate";
import { AUTH } from "@/constants/testIds";

export const UserMenu = () => {
  const { user, signOut } = useAuth();
  return (
    <div data-testid={AUTH.userMenu} className="flex items-center gap-2 shrink-0">
      {user.picture
        ? <img src={user.picture} alt="" referrerPolicy="no-referrer" className="h-8 w-8 rounded-full border border-[var(--pc-border)]" />
        : <div className="h-8 w-8 rounded-full bg-[var(--pc-surface2)] grid place-items-center text-xs font-bold">{user.name?.[0]}</div>}
      <span data-testid={AUTH.userName} className="hidden lg:block text-sm text-[var(--pc-text2)] max-w-[140px] truncate">{user.name}</span>
      <button data-testid={AUTH.logoutButton} onClick={signOut} title="Sign out"
        className="h-8 w-8 grid place-items-center rounded-md text-[var(--pc-muted)] hover:text-[var(--pc-text)] hover:bg-[var(--pc-surface2)] transition-colors duration-150">
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
};
