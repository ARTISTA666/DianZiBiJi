"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Settings } from "lucide-react";
import { useAuthStore } from "@/stores";

export function MainNav() {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const canAdmin = user?.role === "super_admin";

  const links = [
    { href: "/projects", label: "项目", icon: LayoutDashboard },
    ...(canAdmin ? [{ href: "/admin", label: "管理", icon: Settings }] : []),
  ];

  return (
    <nav className="flex items-center gap-1.5 p-1 rounded-xl bg-muted/50 border border-border/40 w-fit">
      {links.map(({ href, label, icon: Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`inline-flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all ${
              active
                ? "bg-card text-foreground shadow-subtle font-semibold"
                : "text-muted-foreground hover:text-foreground hover:bg-background/60"
            }`}
          >
            <Icon size={14} className={active ? "text-primary" : "text-muted-foreground"} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
