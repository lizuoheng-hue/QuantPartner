"use client";

import { LogOut } from "lucide-react";
import { useEffect } from "react";
import { getAccessToken, setAccessToken } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

function clearQuantPartnerStorage() {
  setAccessToken(null);
  for (let index = window.localStorage.length - 1; index >= 0; index -= 1) {
    const key = window.localStorage.key(index);
    if (key?.startsWith("quantpartner:workspace:")) {
      window.localStorage.removeItem(key);
    }
  }
}

export default function LogoutPage() {
  useEffect(() => {
    let cancelled = false;
    const token = getAccessToken();
    const finish = () => {
      if (cancelled) return;
      clearQuantPartnerStorage();
      window.location.replace("/");
    };

    if (!token) {
      finish();
      return () => { cancelled = true; };
    }

    fetch(`${API_URL}/api/v1/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined).finally(finish);

    return () => { cancelled = true; };
  }, []);

  return (
    <main className="auth-loading">
      <LogOut size={42} />
      <span>正在退出登录…</span>
    </main>
  );
}
