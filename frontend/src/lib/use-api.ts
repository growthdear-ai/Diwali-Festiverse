"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Minimal fetch-state hook: data / error / loading plus reload and local mutate. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = [], opts: { pollMs?: number } = {}) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const requestId = useRef(0);

  const load = useCallback(async (silent = false) => {
    const id = ++requestId.current;
    if (!silent) {
      // Deps changed: drop the previous resource so it never shows under the new id.
      setData(undefined);
      setLoading(true);
    }
    try {
      const result = await fetcherRef.current();
      if (id !== requestId.current) return; // a newer request superseded this one
      setData(result);
      setError(null);
    } catch (e) {
      if (id !== requestId.current) return;
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch-on-mount is this hook's purpose
    load();
    if (!opts.pollMs) return;
    const t = setInterval(() => load(true), opts.pollMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, opts.pollMs, ...deps]);

  return { data, error, loading, reload: () => load(true), setData };
}
