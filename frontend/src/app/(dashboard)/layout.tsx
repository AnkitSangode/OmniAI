
"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import {
  LayoutDashboard,
  MessageSquare,
  Image as ImageIcon,
  Mic,
  Video,
  Sparkles,
  LogOut,
  UserCircle,
} from "lucide-react";

import { useAuth } from "@/context/auth-context";

const navigation = [
  {
    name: "Dashboard",
    href: "/dashboard",
    icon: LayoutDashboard,
  },
  {
    name: "Text AI",
    href: "/text",
    icon: MessageSquare,
  },
  {
    name: "Image AI",
    href: "/image",
    icon: ImageIcon,
  },
  {
    name: "Audio AI",
    href: "/audio",
    icon: Mic,
  },
  {
    name: "Video AI",
    href: "/video",
    icon: Video,
  },
];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, logout } = useAuth();

  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  // Wait until authentication initialization completes.
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#09090b] text-white">
        <div className="flex flex-col items-center gap-3">
          <Sparkles className="h-8 w-8 animate-pulse text-violet-400" />
          <p className="text-sm text-zinc-400">
            Loading OmniAI...
          </p>
        </div>
      </div>
    );
  }

  // Prevent protected content from rendering without authentication.
  if (!user) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-[#09090b] text-white">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-white/10 bg-[#101014]">
        {/* Logo */}
        <div className="flex h-20 items-center gap-3 border-b border-white/10 px-6">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-600">
            <Sparkles className="h-6 w-6 text-white" />
          </div>

          <div>
            <h1 className="text-lg font-bold tracking-tight">
              OmniAI
            </h1>
            <p className="text-xs text-zinc-500">
              Multimodal AI Platform
            </p>
          </div>
        </div>

        {/* Navigation */}
        <div className="flex-1 px-4 py-6">
          <p className="mb-4 px-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            Workspace
          </p>

          <nav className="space-y-2">
            {navigation.map((item) => {
              const Icon = item.icon;

              const isActive =
                pathname === item.href ||
                (item.href !== "/dashboard" &&
                  pathname.startsWith(`${item.href}/`));

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-lg px-3 py-3 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-violet-600/15 text-violet-400"
                      : "text-zinc-400 hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* User section */}
        <div className="border-t border-white/10 p-4">
          <div className="mb-4 flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-zinc-800">
              <UserCircle className="h-6 w-6 text-zinc-300" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-white">
                {user.full_name}
              </p>
              <p className="truncate text-xs text-zinc-500">
                {user.email}
              </p>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-3 text-sm text-zinc-400 transition-colors hover:bg-red-500/10 hover:text-red-400"
          >
            <LogOut className="h-5 w-5" />
            Logout
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-64 min-h-screen flex-1">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-white/10 bg-[#09090b]/90 px-8 backdrop-blur">
          <div>
            <h2 className="text-sm font-medium text-zinc-300">
              {navigation.find((item) => item.href === pathname)?.name ??
                "Workspace"}
            </h2>
          </div>

          <div className="flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            <span className="text-xs text-zinc-400">
              Workspace Active
            </span>
          </div>
        </header>

        <div className="p-8">
          {children}
        </div>
      </main>
    </div>
  );
}
