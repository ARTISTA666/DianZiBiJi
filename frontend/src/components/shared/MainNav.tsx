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
    <nav className="flex gap-1">
      {links.map(({ href, label, icon: Icon }) => {
        const active = pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              active
                ? "bg-primary/10 text-primary"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            }`}
          >
            <Icon size={16} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
