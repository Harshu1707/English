"use client";
import Link from "next/link";
import { useEffect } from "react";
import { BookOpen, ChartNoAxesCombined, ClipboardCheck, LayoutDashboard, LogOut, Mic2, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./AuthProvider";
import { useProgress } from "./ProgressProvider";
import type { Role } from "../lib/api";
type NavLink = { href: string; label: string; short?: string; icon: typeof LayoutDashboard };
// Admin-only destinations, appended for signed-in admins. The pages and the API enforce the role themselves.
const adminLinks: NavLink[] = [{ href: "/admin", label: "Admin", icon: ShieldCheck }, { href: "/admin/content-progress", label: "Content Progress", short: "Content", icon: ClipboardCheck }];
const links: NavLink[] = [{ href: "/dashboard", label: "Overview", icon: LayoutDashboard }, { href: "/lessons", label: "Lessons", icon: BookOpen }, { href: "/practice", label: "Practice", icon: Mic2 }, { href: "/progress", label: "Progress", icon: ChartNoAxesCombined }];
export function Brand() { return <Link className="brand" href="/"><span className="brand-mark"><Sparkles size={17}/></span>verba</Link>; }
// The sidebar streak is the signed-in teacher's real streak, recomputed by the backend.
function StreakNote() { const { summary } = useProgress(); const days = summary?.current_streak ?? 0;
  return <Link className="side-note" href="/profile"><span>STREAK</span><strong>{days} {days === 1 ? "day" : "days"}</strong><p>{days > 0 ? "Keep your rhythm going." : "Your next activity starts it."}</p></Link>; }
function initials(name: string) { return name.trim().split(/\s+/).slice(0, 2).map(w => w[0]?.toUpperCase() ?? "").join("") || "?"; }
export default function SiteShell({ children, requireRole }: {children: React.ReactNode; requireRole?: Role}) { const path = usePathname(); const router = useRouter(); const { user, loading, logout } = useAuth();
  // Every page inside the shell is protected: signed-out visitors go to /login and come back afterwards.
  useEffect(() => { if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [loading, user, path, router]);
  if (loading || !user) return <div className="auth-loading" role="status" aria-live="polite"><Brand/><p>Loading your workspace…</p></div>;
  const forbidden = requireRole && user.role !== requireRole;
  const navLinks = user.role === "admin" ? [...links, ...adminLinks] : links;
  return <div className="app-shell"><aside className="side"><Brand/><nav>{navLinks.map(({href,label,icon:Icon})=><Link key={href} className={path===href ? "nav active" : "nav"} href={href}><Icon size={18}/>{label}</Link>)}</nav><StreakNote/><div className="user"><Link className="user-link" href="/profile" title="Open your profile"><div className="avatar">{initials(user.full_name)}</div><div><b>{user.full_name}</b><small>{user.role === "admin" ? "Admin" : "Teacher"}</small></div></Link><button className="logout-button" onClick={logout} aria-label="Sign out" title="Sign out"><LogOut size={16}/></button></div></aside><main className="app-main">{forbidden ? <section className="card forbidden"><p className="eyebrow">ADMIN ONLY</p><h2>You don’t have access to this page.</h2><p>Your account is signed in as a {user.role}. Ask an administrator if you need access.</p><Link className="button" href="/dashboard">Back to overview</Link></section> : children}</main><nav className={user.role === "admin" ? "mobile-nav has-admin" : "mobile-nav"}>{navLinks.map(({href,label,short,icon:Icon})=><Link key={href} className={path===href ? "active" : ""} href={href}><Icon size={19}/><span>{short ?? label}</span></Link>)}<Link className={path==="/profile" ? "active" : ""} href="/profile"><UserRound size={19}/><span>Profile</span></Link><button className="mobile-logout" onClick={logout}><LogOut size={19}/><span>Sign out</span></button></nav></div>; }
