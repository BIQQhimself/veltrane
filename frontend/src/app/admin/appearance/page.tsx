"use client";

import * as React from "react";
import { Paintbrush, RotateCcw, Save, Undo2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorNote, Skeleton } from "@/components/ui/data";
import { Field, Input } from "@/components/ui/input";
import { Panel, PanelBody, PanelHeader, SectionHeading } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";
import { useTheme, publishTheme } from "@/components/app/theme-provider";
import {
  contrastRatio,
  DEFAULT_BRANDING,
  DEFAULT_COLORS,
  deriveVars,
  type ThemeBranding,
  type ThemeColors,
  type ThemePayload,
} from "@/lib/theme";

type Response = { theme: ThemePayload; tokens: string[]; branding_defaults: ThemeBranding };

const GROUPS: Array<{ title: string; hint: string; keys: string[] }> = [
  { title: "Surfaces", hint: "Page, cards and raised panels.", keys: ["background", "surface", "surface_raised", "border"] },
  { title: "Text", hint: "Body copy and secondary labels.", keys: ["text", "text_muted", "button_text"] },
  { title: "Action", hint: "Primary buttons, links and focus rings.", keys: ["primary", "primary_hover", "secondary"] },
  { title: "Accent", hint: "The restrained highlight used for premium details.", keys: ["accent"] },
  {
    title: "Charts and results",
    hint: "Candles, grid lines and profit/loss colouring.",
    keys: ["chart_up", "chart_down", "chart_grid", "chart_line", "gain", "loss", "warn"],
  },
];

const LABELS: Record<string, string> = {
  background: "Background",
  surface: "Surface",
  surface_raised: "Raised surface",
  border: "Border",
  text: "Text",
  text_muted: "Muted text",
  button_text: "Button label",
  primary: "Primary",
  primary_hover: "Primary (hover)",
  secondary: "Secondary",
  accent: "Accent",
  chart_up: "Up candle",
  chart_down: "Down candle",
  chart_grid: "Chart grid",
  chart_line: "Chart line",
  gain: "Profit",
  loss: "Loss",
  warn: "Warning",
};

export default function AdminAppearancePage() {
  const toast = useToast();
  const { theme: liveTheme, preview, refresh } = useTheme();
  const settings = useApi<Response>((signal) => api("/admin/theme", { signal }));

  const [colors, setColors] = React.useState<ThemeColors>(DEFAULT_COLORS);
  const [branding, setBranding] = React.useState<ThemeBranding>(DEFAULT_BRANDING);
  const [busy, setBusy] = React.useState(false);
  const [dirty, setDirty] = React.useState(false);

  React.useEffect(() => {
    if (settings.data) {
      setColors({ ...DEFAULT_COLORS, ...settings.data.theme.colors });
      setBranding({ ...DEFAULT_BRANDING, ...settings.data.theme.branding });
      setDirty(false);
    }
  }, [settings.data]);

  // Live preview, so the operator sees the change before publishing it.
  React.useEffect(() => {
    preview({ colors, branding });
  }, [colors, branding, preview]);

  const revert = React.useCallback(() => {
    setColors({ ...DEFAULT_COLORS, ...(settings.data?.theme.colors ?? {}) });
    setBranding({ ...DEFAULT_BRANDING, ...(settings.data?.theme.branding ?? {}) });
    setDirty(false);
  }, [settings.data]);

  async function save() {
    setBusy(true);
    try {
      const result = await api<{ theme: ThemePayload }>("/admin/theme", {
        method: "PUT",
        body: { colors, branding },
      });
      toast.success("Appearance published", "Subscribers see the new palette on their next page load.");
      publishTheme(result.theme);
      setDirty(false);
      settings.refetch();
      await refresh();
    } catch (error) {
      toast.error("Could not publish", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    try {
      const result = await api<{ theme: ThemePayload }>("/admin/theme", { method: "PUT", body: { reset: true } });
      toast.success("Reset to the shipped palette");
      publishTheme(result.theme);
      setColors(DEFAULT_COLORS);
      setBranding(DEFAULT_BRANDING);
      setDirty(false);
      settings.refetch();
      await refresh();
    } catch (error) {
      toast.error("Reset failed", errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  const bodyContrast = contrastRatio(colors.text ?? "#fff", colors.background ?? "#000");
  const buttonContrast = contrastRatio(colors.button_text ?? "#fff", colors.primary ?? "#000");
  const warnings = [
    bodyContrast < 4.5 ? `Body text on background is ${bodyContrast.toFixed(2)}:1 — below the 4.5:1 accessibility floor.` : null,
    buttonContrast < 4.5 ? `Button label on primary is ${buttonContrast.toFixed(2)}:1 — below the 4.5:1 floor.` : null,
  ].filter(Boolean) as string[];

  return (
    <div className="space-y-4">
      <SectionHeading
        title="Appearance"
        description="The palette and branding every subscriber sees. Changes publish from the database — no redeploy — and every change is audited."
        action={
          <Badge tone={liveTheme.source === "admin" ? "info" : "neutral"}>
            {liveTheme.source === "admin" ? "Custom palette live" : "Shipped palette"}
          </Badge>
        }
      />

      {settings.error ? <ErrorNote message={settings.error} onRetry={settings.refetch} /> : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          {settings.loading && !settings.data ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-28" />
              ))}
            </div>
          ) : (
            GROUPS.map((group) => (
              <Panel key={group.title}>
                <PanelHeader
                  title={group.title}
                  subtitle={group.hint}
                  action={<Paintbrush className="h-3.5 w-3.5 text-paper-faint" aria-hidden />}
                />
                <PanelBody className="grid gap-3 sm:grid-cols-2">
                  {group.keys.map((key) => (
                    <div key={key} className="flex items-center gap-3">
                      <input
                        type="color"
                        value={colors[key] ?? "#000000"}
                        onChange={(event) => {
                          setColors((current) => ({ ...current, [key]: event.target.value }));
                          setDirty(true);
                        }}
                        aria-label={`${LABELS[key] ?? key} colour`}
                        className="h-9 w-11 shrink-0 cursor-pointer rounded-lg border border-line bg-transparent p-0.5"
                      />
                      <label className="min-w-0 flex-1">
                        <span className="block text-2xs text-paper">{LABELS[key] ?? key}</span>
                        <input
                          value={colors[key] ?? ""}
                          onChange={(event) => {
                            setColors((current) => ({ ...current, [key]: event.target.value }));
                            setDirty(true);
                          }}
                          spellCheck={false}
                          aria-label={`${LABELS[key] ?? key} hex value`}
                          className="num mt-0.5 w-full rounded border border-line-soft bg-obsidian-900 px-1.5 py-0.5 text-3xs text-paper-muted outline-none focus:border-champagne-500/60"
                        />
                      </label>
                    </div>
                  ))}
                </PanelBody>
              </Panel>
            ))
          )}

          <Panel>
            <PanelHeader title="Branding" subtitle="Name, mark and tagline shown in the workspace." />
            <PanelBody className="grid gap-3 sm:grid-cols-2">
              <Field label="Product name" hint="Used in the wordmark.">
                <Input
                  value={branding.product_name}
                  maxLength={40}
                  onChange={(event) => {
                    setBranding((current) => ({ ...current, product_name: event.target.value }));
                    setDirty(true);
                  }}
                />
              </Field>
              <Field label="Logo mark" hint="One to three characters.">
                <Input
                  value={branding.logo_mark}
                  maxLength={3}
                  onChange={(event) => {
                    setBranding((current) => ({ ...current, logo_mark: event.target.value }));
                    setDirty(true);
                  }}
                />
              </Field>
              <Field label="Tagline" hint="Optional line under the name.">
                <Input
                  value={branding.tagline}
                  maxLength={80}
                  onChange={(event) => {
                    setBranding((current) => ({ ...current, tagline: event.target.value }));
                    setDirty(true);
                  }}
                />
              </Field>
            </PanelBody>
          </Panel>
        </div>

        <div className="space-y-3 lg:sticky lg:top-20 lg:self-start">
          <Panel>
            <PanelHeader title="Preview" />
            <PanelBody className="space-y-3">
              <div
                className="rounded-xl border border-line p-3"
                style={{ background: `rgb(${deriveVars(colors)["vt-bg"]})` }}
              >
                <p className="text-2xs" style={{ color: colors.text }}>
                  Body text on the page background.
                </p>
                <p className="mt-0.5 text-3xs" style={{ color: colors.text_muted }}>
                  Secondary copy, captions and hints.
                </p>
                <div className="mt-2 flex items-center gap-1.5">
                  <span
                    className="rounded-md px-2 py-1 text-3xs font-medium"
                    style={{ background: colors.primary, color: colors.button_text }}
                  >
                    Call
                  </span>
                  <span
                    className="rounded-md px-2 py-1 text-3xs"
                    style={{ background: colors.surface_raised, color: colors.gain }}
                  >
                    +12.4%
                  </span>
                  <span
                    className="rounded-md px-2 py-1 text-3xs"
                    style={{ background: colors.surface_raised, color: colors.loss }}
                  >
                    −4.1%
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                <div className="rounded-lg border border-line-soft p-2 text-center">
                  <p className="text-3xs" style={{ color: colors.text_muted }}>
                    {branding.logo_mark || "V"}
                  </p>
                  <p className="text-2xs" style={{ color: colors.accent }}>
                    {branding.product_name || "VELTRANE"}
                  </p>
                </div>
                <div className="rounded-lg border border-line-soft p-2 text-center">
                  <p className="text-3xs" style={{ color: colors.text_muted }}>
                    {bodyContrast.toFixed(1)}:1
                  </p>
                  <p className="text-2xs" style={{ color: colors.text }}>
                    Body contrast
                  </p>
                </div>
              </div>
              {warnings.length ? (
                <ul className="space-y-1 rounded-lg border border-warn/30 bg-warn/[0.07] p-2.5">
                  {warnings.map((warning) => (
                    <li key={warning} className="text-3xs leading-relaxed text-warn">
                      {warning}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-3xs text-paper-faint">Contrast checks pass at 4.5:1 or better.</p>
              )}
            </PanelBody>
          </Panel>

          <div className="flex flex-col gap-2">
            <Button onClick={save} loading={busy} disabled={!dirty}>
              <Save className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Publish palette
            </Button>
            <Button variant="ghost" onClick={revert} disabled={!dirty || busy}>
              <Undo2 className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Discard changes
            </Button>
            <Button variant="ghost" onClick={reset} loading={busy}>
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden /> Reset to shipped palette
            </Button>
          </div>

          <p className="text-3xs leading-relaxed text-paper-faint">
            Publishing writes one audited row. Subscribers pick it up on their next page load, and a change
            can be rolled back the same way. Nothing here can alter trading behaviour.
          </p>
        </div>
      </div>
    </div>
  );
}
