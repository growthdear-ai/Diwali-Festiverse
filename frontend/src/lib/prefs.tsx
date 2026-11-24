"use client";

import { createContext, useContext, useEffect, useState } from "react";

// Per-device preferences (localStorage). Not shared across devices.
export type Lang = "en" | "hi";

export interface Prefs {
  lang: Lang;
  browserNotifications: boolean;
  alertSound: boolean;
  readAlerts: number[];
}

const DEFAULTS: Prefs = { lang: "en", browserNotifications: false, alertSound: true, readAlerts: [] };
const KEY = "nazar.prefs";

const dict = {
  en: {
    dashboard: "Overview",
    rooms: "Rooms",
    watches: "Watches",
    alerts: "Alerts",
    settings: "Settings",
    createRoom: "Create room",
    conversations: "Chat",
    newWatch: "New watch",
    welcome: "Welcome back",
    logout: "Log out",
  },
  hi: {
    dashboard: "डैशबोर्ड",
    rooms: "रूम",
    watches: "निगरानी",
    alerts: "अलर्ट",
    settings: "सेटिंग्स",
    createRoom: "रूम बनाएँ",
    conversations: "चैट",
    newWatch: "नई निगरानी",
    welcome: "फिर से स्वागत है",
    logout: "लॉग आउट",
  },
} as const;

export type TKey = keyof (typeof dict)["en"];

interface PrefsContextValue {
  prefs: Prefs;
  update: (patch: Partial<Prefs>) => void;
  t: (key: TKey) => string;
  markRead: (alertId: number) => void;
  isRead: (alertId: number) => boolean;
}

const PrefsContext = createContext<PrefsContextValue | null>(null);

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const [prefs, setPrefs] = useState<Prefs>(DEFAULTS);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate from storage after mount
      if (raw) setPrefs({ ...DEFAULTS, ...JSON.parse(raw) });
    } catch {}
  }, []);

  useEffect(() => {
    document.documentElement.lang = prefs.lang;
  }, [prefs.lang]);

  const update = (patch: Partial<Prefs>) =>
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {}
      return next;
    });

  const value: PrefsContextValue = {
    prefs,
    update,
    t: (key) => dict[prefs.lang][key],
    markRead: (id) => {
      if (!prefs.readAlerts.includes(id)) update({ readAlerts: [...prefs.readAlerts, id].slice(-500) });
    },
    isRead: (id) => prefs.readAlerts.includes(id),
  };

  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs() {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs must be used inside <PrefsProvider>");
  return ctx;
}
