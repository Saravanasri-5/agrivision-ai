"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Moon, Sprout, Sun } from "lucide-react";

export default function Navbar() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    let saved: string | null = null;
    try { saved = localStorage.getItem("theme"); } catch {}
    const d = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
  }, []);
  const toggle = () => {
    const d = !dark;
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
    try { localStorage.setItem("theme", d ? "dark" : "light"); } catch {}
  };
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-5 dark:border-slate-800 dark:bg-slate-900">
      <Link href="/" className="flex items-center gap-2 font-bold tracking-tight">
        <span className="rounded-lg bg-brand-600 p-1.5 text-white"><Sprout size={18} /></span>
        AGRIVISION <span className="text-brand-600">AI</span>
      </Link>
      <nav className="flex items-center gap-3 text-sm">
        <Link href="/#features" className="hidden text-slate-600 hover:text-brand-600 dark:text-slate-300 sm:block">Features</Link>
        <Link href="/analysis" className="btn btn-primary !py-1.5">Launch Analysis</Link>
        <button onClick={toggle} aria-label="Toggle theme" className="btn btn-ghost !p-2">
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </nav>
    </header>
  );
}
