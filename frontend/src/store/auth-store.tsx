"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { refreshCustomerIdentity } from "@/lib/api/agent";
import {
  getProfile as apiGetProfile,
  login as apiLogin,
  logout as apiLogout,
  me as apiMe,
  register as apiRegister,
  staffLogin as apiStaffLogin,
  updateProfile as apiUpdateProfile,
  type AuthUser,
  type UpdateProfilePayload,
  type UserProfile,
} from "@/lib/api/auth";

type AuthStatus = "loading" | "authenticated" | "anonymous";

type AuthStore = {
  status: AuthStatus;
  user: AuthUser | null;
  profile: UserProfile | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /**
   * Nhận phiên đã đăng nhập ở NƠI KHÁC (ví dụ form staff-login tự gọi
   * `staffApi.login` + `me()`). Store chỉ hỏi `/me` MỘT lần lúc mount, nên nếu
   * không báo lại thì store vẫn đinh ninh "anonymous" — RoleGuard của /admin
   * lặng lẽ đá ngược về màn đăng nhập dù backend đã cấp cookie (lỗi Sếp gặp
   * 2026-08-31: "quay lại màn đăng nhập không có thông báo gì").
   */
  adoptSession: (user: AuthUser) => Promise<void>;
  refreshProfile: () => Promise<void>;
  saveProfile: (payload: UpdateProfilePayload) => Promise<UserProfile>;
};

const AuthContext = createContext<AuthStore | null>(null);

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);

  const refreshProfile = useCallback(async (): Promise<void> => {
    try {
      const data = await apiGetProfile();
      setProfile(data);
    } catch {
      setProfile(null);
    }
  }, []);

  useEffect(() => {
    let active = true;
    apiMe()
      .then(async (current) => {
        if (!active) return;
        setUser(current);
        setStatus(current ? "authenticated" : "anonymous");
        if (current && (current.role === "customer" || current.role === "advisor")) {
          const prof = await apiGetProfile().catch(() => null);
          if (active) setProfile(prof);
        } else {
          setProfile(null);
        }
      })
      .catch(() => {
        if (active) {
          setStatus("anonymous");
          setProfile(null);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    try {
      await apiLogin(email, password);
    } catch {
      await apiStaffLogin(email, password);
    }
    const current = await apiMe();
    setUser(current);
    setStatus(current ? "authenticated" : "anonymous");
    if (current && (current.role === "customer" || current.role === "advisor")) {
      const prof = await apiGetProfile().catch(() => null);
      setProfile(prof);
    }
  }, []);

  const adoptSession = useCallback(async (current: AuthUser) => {
    setUser(current);
    setStatus("authenticated");
    if (current.role === "customer" || current.role === "advisor") {
      const prof = await apiGetProfile().catch(() => null);
      setProfile(prof);
    } else {
      setProfile(null);
    }
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await apiRegister(email, password);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setUser(null);
    setProfile(null);
    setStatus("anonymous");
  }, []);

  const saveProfile = useCallback(async (payload: UpdateProfilePayload): Promise<UserProfile> => {
    const updated = await apiUpdateProfile(payload);
    setProfile(updated);
    // Khách sửa tên/SĐT/địa chỉ ở /account: tư vấn viên thấy bản mới ngay (plan §19).
    if (updated.role === "customer") await refreshCustomerIdentity().catch(() => undefined);
    return updated;
  }, []);

  const store = useMemo<AuthStore>(
    () => ({ status, user, profile, login, register, logout, adoptSession, refreshProfile, saveProfile }),
    [status, user, profile, login, register, logout, adoptSession, refreshProfile, saveProfile],
  );

  return <AuthContext.Provider value={store}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthStore {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
