const TOKEN_KEY = "zealead_token";
const COOKIE_MAX_AGE = 7 * 24 * 60 * 60; // 7 days (seconds), same as the server-side token lifetime

export interface CurrentUser {
  id: string;
  name: string;
  username: string;
  email: string;
  avatar: string;
  role: string;
}

export const auth = {
  getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem(TOKEN_KEY);
  },

  setToken(token: string): void {
    localStorage.setItem(TOKEN_KEY, token);
    // Mirrored into a cookie for the Next dev-server proxy (src/proxy.ts); the API itself only reads the header.
    document.cookie = `${TOKEN_KEY}=${encodeURIComponent(token)}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Strict`;
  },

  clearToken(): void {
    localStorage.removeItem(TOKEN_KEY);
    document.cookie = `${TOKEN_KEY}=; path=/; max-age=0`;
  },

  // Display only: reads the signed token's payload without verifying it (the server verifies every request).
  getCurrentUser(): CurrentUser | null {
    const token = this.getToken();
    if (!token) return null;
    try {
      const parts = token.split(".");
      if (parts.length !== 3) return null;
      const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
      const username: string = payload.sub ?? "user";
      return { id: String(payload.uid ?? ""), name: username, username, email: "", avatar: "", role: payload.role ?? "member" };
    } catch {
      return null;
    }
  },
};
