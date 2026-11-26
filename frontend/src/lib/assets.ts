export const CLASS_LABEL: Record<string, string> = {
  crypto: "Crypto",
  forex: "Forex",
  stock: "Equities",
  commodity: "Metals",
};

/** Crypto leads because it is the first market with a live-trading path. */
export const CLASS_ORDER: Record<string, number> = { crypto: 0, forex: 1, stock: 2, commodity: 3 };

export function byAssetClass<T extends { asset_class: string; symbol: string }>(a: T, b: T): number {
  return (
    (CLASS_ORDER[a.asset_class] ?? 9) - (CLASS_ORDER[b.asset_class] ?? 9) ||
    a.symbol.localeCompare(b.symbol)
  );
}
