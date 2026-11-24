"use client";

import { Bell, Globe, LogOut, Shield, Trash2, User } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { PageContainer } from "@/components/app-shell";
import { PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/misc";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import { usePrefs, type Lang } from "@/lib/prefs";
import { cn } from "@/lib/utils";

function Row({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
      </div>
      {children}
    </div>
  );
}

function Section({ icon: Icon, title, children }: { icon: React.ComponentType<{ className?: string }>; title: string; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="size-4 text-primary" /> {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="divide-y divide-border">{children}</CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { user, logout } = useAuth();
  const { prefs, update, t } = usePrefs();
  const [permission, setPermission] = useState(() => (typeof Notification !== "undefined" ? Notification.permission : "denied"));

  async function toggleBrowserNotifications(on: boolean) {
    if (!on) return update({ browserNotifications: false });
    if (typeof Notification === "undefined") return toast.error("This browser doesn't support notifications.");
    const result = await Notification.requestPermission();
    setPermission(result);
    if (result === "granted") {
      update({ browserNotifications: true });
      toast.success("Notifications on for this device");
    } else toast.error("Notifications are blocked. Allow them in your browser settings.");
  }

  function clearLocal() {
    update({ readAlerts: [] });
    toast.success("Cleared read history on this device");
  }

  return (
    <PageContainer className="max-w-2xl">
      <PageHeader title={t("settings")} />
      <div className="space-y-4">
        <Section icon={User} title="Profile">
          <Row title="Name">
            <span className="text-sm text-muted-foreground">{user?.name}</span>
          </Row>
          <Row title="Email">
            <span className="truncate text-sm text-muted-foreground">{user?.email}</span>
          </Row>
          <Row title="Member since">
            <span className="text-sm text-muted-foreground">{dateTime(user?.created_at)}</span>
          </Row>
        </Section>

        <Section icon={Bell} title="Notifications">
          <Row title="Browser notifications" description={permission === "denied" ? "Blocked in browser settings" : "Get notified on this device when Nazar posts an alert"}>
            <Switch checked={prefs.browserNotifications && permission === "granted"} onCheckedChange={toggleBrowserNotifications} aria-label="Browser notifications" />
          </Row>
          <Row title="Alert sound" description="Play a sound for new alerts while the app is open">
            <Switch checked={prefs.alertSound} onCheckedChange={(v) => update({ alertSound: v })} aria-label="Alert sound" />
          </Row>
        </Section>

        <Section icon={Globe} title="Language">
          <Row title="App language" description="Navigation and labels. Alerts appear in the language the backend sends.">
            <div className="flex rounded-[10px] border border-border-strong p-0.5">
              {(
                [
                  ["en", "English"],
                  ["hi", "हिन्दी"],
                ] as [Lang, string][]
              ).map(([code, label]) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => update({ lang: code })}
                  aria-pressed={prefs.lang === code}
                  className={cn("cursor-pointer rounded-[8px] px-3 py-1.5 text-[13px] font-medium transition-colors", prefs.lang === code ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground")}
                >
                  {label}
                </button>
              ))}
            </div>
          </Row>
        </Section>

        <Section icon={Shield} title="Privacy">
          <Row title="Who sees your data" description="Your name and email are visible to members of rooms you join. Watches and alerts are visible to everyone in that room.">
            <span />
          </Row>
          <Row title="Read history on this device" description="Which alerts you've opened is stored only in this browser.">
            <Button variant="secondary" size="sm" onClick={clearLocal}>
              <Trash2 /> Clear
            </Button>
          </Row>
        </Section>

        <Card className="p-5">
          <Button variant="danger" className="w-full sm:w-auto" onClick={logout}>
            <LogOut /> {t("logout")}
          </Button>
        </Card>
      </div>
    </PageContainer>
  );
}
