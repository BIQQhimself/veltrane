"use client";

import * as React from "react";

const KEY = "veltrane:favourites";
const MAX = 12;

/** Pure helpers so the ordering rules can be tested without a DOM. */
export function toggleFavourite(list: string[], symbol: string): string[] {
  return list.includes(symbol) ? list.filter((item) => item !== symbol) : [...list, symbol].slice(-MAX);
}

export function orderFavourites(list: string[], available: string[]): string[] {
  const known = new Set(available);
  return list.filter((symbol) => known.has(symbol));
}

/**
 * Favourite instruments, kept on the device. A watchlist is a personal preference, not
 * account data, so it stays local and works before the first server round-trip.
 */
export function useFavourites() {
  const [favourites, setFavourites] = React.useState<string[]>([]);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(KEY);
      const parsed = raw ? (JSON.parse(raw) as unknown) : [];
      if (Array.isArray(parsed)) setFavourites(parsed.filter((item): item is string => typeof item === "string"));
    } catch {
      setFavourites([]);
    }
    setLoaded(true);
  }, []);

  const persist = React.useCallback((next: string[]) => {
    setFavourites(next);
    try {
      window.localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      // Private mode: the list simply does not survive a reload.
    }
  }, []);

  const toggle = React.useCallback(
    (symbol: string) => {
      setFavourites((current) => {
        const next = toggleFavourite(current, symbol);
        try {
          window.localStorage.setItem(KEY, JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [],
  );

  return { favourites, loaded, toggle, setFavourites: persist };
}
