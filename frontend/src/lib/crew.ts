/**
 * Crew identity encoding. Colour follows the crew member, never their rank, and is backed by
 * a dash pattern plus direct labels so identity never relies on colour alone.
 * Palette validated (dark, hull surface #0c1a2e, all pairs): CVD ΔE 7.9, normal-vision ΔE 15.1.
 */
const CREW_ORDER = ["AST-01", "AST-02", "AST-03", "AST-04"];
const COLORS = ["var(--crew-1)", "var(--crew-2)", "var(--crew-3)", "var(--crew-4)"];
const DASHES = ["0", "7 3", "2 3", "10 3 2 3"];

function slot(id: string): number {
  const i = CREW_ORDER.indexOf(id);
  return i === -1 ? 0 : i;
}

export function crewColor(id: string): string {
  return COLORS[slot(id)];
}

export function crewDash(id: string): string {
  return DASHES[slot(id)];
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function surname(name: string): string {
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1];
}
