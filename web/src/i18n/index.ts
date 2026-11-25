// UI text layer kept from ZeaLead: t("Text") returns the English source text and fills
// {placeholders}. To translate ZeaLead, add locales/<code>.json and a lookup here.

export type Locale = "en";
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALES: { code: Locale; label: string }[] = [{ code: "en", label: "English" }];
export const locale: Locale = "en";
export const intlLocale = "en-US";

export type TVars = Record<string, string | number>;

export function t(key: string, vars?: TVars): string {
  if (!vars) return key;
  return key.replace(/\{(\w+)\}/g, (m, name: string) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : m,
  );
}

export function setLocale(_next: Locale) {}
