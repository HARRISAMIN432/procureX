export const money = (value: string | number | undefined, currency = "PKR") =>
  new Intl.NumberFormat("en-PK", { style: "currency", currency, maximumFractionDigits: 2 }).format(Number(value ?? 0));

export const shortDate = (value?: string) => value ? new Intl.DateTimeFormat("en-PK", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)) : "—";

export const relativeDate = (value?: string) => {
  if (!value) return "—";
  const days = Math.round((new Date(value).getTime() - Date.now()) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(days, "day");
};

export const humanize = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

export const initials = (value: string) => value.split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("");
