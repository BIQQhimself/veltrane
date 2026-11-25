"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";

type State<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

export function useApi<T>(fetcher: (signal: AbortSignal) => Promise<T>, deps: unknown[] = []) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const run = useCallback(async (signal: AbortSignal) => {
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fetcherRef.current(signal);
      if (signal.aborted) return;
      setState({ data, error: null, loading: false });
    } catch (error) {
      if (signal.aborted) return;
      if ((error as Error).name === "AbortError") return;
      setState({ data: null, error: errorMessage(error), loading: false });
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void run(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const refetch = useCallback(() => {
    const controller = new AbortController();
    void run(controller.signal);
  }, [run]);

  return { ...state, refetch, setData: (data: T) => setState({ data, error: null, loading: false }) };
}

export function useInterval(callback: () => void, delay: number | null) {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (delay === null) return;
    const id = setInterval(() => saved.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}
