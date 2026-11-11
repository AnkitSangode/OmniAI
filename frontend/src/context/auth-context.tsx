
"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { authService } from "@/services/auth.service";

import type {
  User,
  LoginPayload,
  RegisterPayload,
} from "@/types/auth";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (
    full_name: string,
    email: string,
    password: string
  ) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore the user's session when the application starts.
  useEffect(() => {
    const initializeAuth = async () => {
      const token = localStorage.getItem("omniai_access_token");

      if (!token) {
        setUser(null);
        setLoading(false);
        return;
      }

      try {
        const currentUser = await authService.getMe();
        setUser(currentUser);
      } catch (error) {
        console.error("Failed to restore user session:", error);

        localStorage.removeItem("omniai_access_token");
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    initializeAuth();
  }, []);

  // Login existing user.
  const login = async (
    email: string,
    password: string
  ): Promise<void> => {
    const payload: LoginPayload = {
      email,
      password,
    };

    const response = await authService.login(payload);

    localStorage.setItem(
      "omniai_access_token",
      response.access_token
    );

    setUser(response.user);
  };

  // Register new user.
  const register = async (
    full_name: string,
    email: string,
    password: string
  ): Promise<void> => {
    const payload: RegisterPayload = {
      full_name,
      email,
      password,
    };

    const response = await authService.register(payload);

    localStorage.setItem(
      "omniai_access_token",
      response.access_token
    );

    setUser(response.user);
  };

  // Logout user.
  const logout = (): void => {
    localStorage.removeItem("omniai_access_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// Custom authentication hook.
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }

  return context;
}
