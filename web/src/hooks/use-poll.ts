"use client";

import { type DependencyList, useCallback, useEffect, useRef, useState } from "react";

import { setVisibleInterval } from "@/lib/polling";

// usePoll loads `fn` now, again whenever deps change, and every `interval` ms while
// the tab is visible (0 = no polling). It keeps the last good data across errors.
export function usePoll<T>(fn: () => Promise<T>, deps: DependencyList, interval = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const reload = useCallback(async () => {
    try {
      const d = await fnRef.current();
      setData(d);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // biome-ignore lint/correctness/useExhaustiveDependencies: deps are the caller's
  useEffect(() => {
    setLoading(true);
    void reload();
    if (!interval) return;
    return setVisibleInterval(reload, interval);
  }, [...deps, interval]);

  return { data, error, loading, reload, setData };
}
