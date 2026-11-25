import {
  Bot,
  Brain,
  Building2,
  LayoutDashboard,
  type LucideIcon,
  Network,
  Plug,
  Radio,
  ScrollText,
  Settings2,
  Target,
  Terminal,
  UserCheck,
  Users,
} from "lucide-react";

import { t } from "@/i18n";

export type NavBadge = "new" | "soon";

export interface NavSubItem {
  id: string;
  title: string;
  url: string;
  icon?: LucideIcon;
  badge?: NavBadge;
  disabled?: boolean;
  newTab?: boolean;
}

interface NavItemBase {
  id: string;
  title: string;
  icon?: LucideIcon;
  badge?: NavBadge;
  disabled?: boolean;
  newTab?: boolean;
  adminOnly?: boolean;
}

export interface NavMainLinkItem extends NavItemBase {
  url: string;
  subItems?: never;
}

export interface NavMainParentItem extends NavItemBase {
  subItems: NavSubItem[];
}

export type NavMainItem = NavMainLinkItem | NavMainParentItem;

export interface NavGroup {
  id: number;
  label?: string;
  items: NavMainItem[];
}

// Same two groups as Leadscout: Functions (the work) and System (configuration).
export const sidebarItems: NavGroup[] = [
  {
    id: 1,
    label: t("Functions"),
    items: [
      { id: "dashboard", title: t("Dashboard"), url: "/dashboard", icon: LayoutDashboard },
      { id: "tasks", title: t("Tasks"), url: "/function/tasks", icon: Target },
      { id: "leads", title: t("Leads"), url: "/function/leads", icon: UserCheck },
      { id: "communities", title: t("Communities"), url: "/function/communities", icon: Network },
      { id: "companies", title: t("Companies"), url: "/function/companies", icon: Building2 },
      { id: "commands", title: t("Tool Execution"), url: "/function/commands", icon: Terminal },
      { id: "llm-records", title: t("LLM Recording"), url: "/function/llm-records", icon: Radio },
    ],
  },
  {
    id: 2,
    label: t("System"),
    items: [
      { id: "llm", title: t("LLM"), url: "/system/llm", icon: Brain },
      { id: "agents", title: t("Agent"), url: "/system/agents", icon: Bot },
      { id: "platforms", title: t("Platforms"), url: "/system/platforms", icon: Plug },
      { id: "users", title: t("Users"), url: "/system/users", icon: Users, adminOnly: true },
      { id: "logs", title: t("Logs"), url: "/system/logs", icon: ScrollText },
      { id: "settings", title: t("System Settings"), url: "/system/settings", icon: Settings2 },
    ],
  },
];
