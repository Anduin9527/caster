// Preferences are optional. Production submission journals deliberately use
// localStorage directly: a failed journal write must prevent submission.
export function readPreference(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePreference(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // A blocked or full browser store must not break an otherwise usable UI.
  }
}
