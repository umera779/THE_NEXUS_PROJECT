import type {
  AddBeneficiaryPayload,
  ApiError,
  ApiResponse,
  Balance,
  Beneficiaries,
  CheckinStatus,
  ForgotPasswordPayload,
  Holdings,
  InitiateFundingResponse,
  LoginPayload,
  Market,
  Portfolio,
  Profile,
  ResetPasswordPayload,
  ResolveBeneficiaryResponse,
  SetupPinPayload,
  SignupPayload,
  TradeHistory,
  VerifyEmailPayload,
  Wallet,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function parseJson<T>(response: Response): Promise<T | null> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  return JSON.parse(text) as T;
}

function getErrorMessage(payload: ApiError | null, fallback: string): string {
  if (!payload) {
    return fallback;
  }
  if (typeof payload.detail === "string" && payload.detail.length > 0) {
    return payload.detail;
  }
  if (typeof payload.message === "string" && payload.message.length > 0) {
    return payload.message;
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {}),
      },
    });

    if (!response.ok) {
      const errorPayload = await parseJson<ApiError>(response);
      return {
        error: getErrorMessage(errorPayload, `Request failed with status ${response.status}`),
      };
    }

    const data = await parseJson<T>(response);
    return { data: data ?? undefined };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Network request failed";
    return { error: message };
  }
}

export const api = {
  signup: (payload: SignupPayload) =>
    request<{ message: string }>("/signup", { method: "POST", body: JSON.stringify(payload) }),

  verifyEmail: (payload: VerifyEmailPayload) =>
    request<{ message: string }>("/verify-email", { method: "POST", body: JSON.stringify(payload) }),

  login: (payload: LoginPayload) =>
    request<{ message: string; is_first_login: boolean; is_pin_set: boolean; role: string }>("/login", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  logout: () => request<{ message: string }>("/logout", { method: "POST" }),

  forgotPassword: (payload: ForgotPasswordPayload) =>
    request<{ message: string }>("/forgot-password", { method: "POST", body: JSON.stringify(payload) }),

  resetPassword: (payload: ResetPasswordPayload) =>
    request<{ message: string }>("/reset-password", { method: "POST", body: JSON.stringify(payload) }),

  profile: () => request<Profile>("/dashboard/profile"),
  balance: () => request<Balance>("/dashboard/balance"),
  wallet: () => request<Wallet>("/dashboard/wallet"),
  portfolio: () => request<Portfolio>("/dashboard/portfolio"),
  market: () => request<Market>("/trading/market"),
  holdings: () => request<Holdings>("/trading/holdings"),
  history: () => request<TradeHistory>("/trading/history"),
  checkinStatus: () => request<CheckinStatus>("/dashboard/checkin"),
  beneficiaries: () => request<Beneficiaries>("/dashboard/beneficiaries"),

  requestPinOtp: () => request<{ message: string }>("/dashboard/request-pin-otp", { method: "POST" }),

  setupPin: (payload: SetupPinPayload) =>
    request<{ message: string }>("/dashboard/setup-pin", { method: "POST", body: JSON.stringify(payload) }),

  setBackupEmail: (backup_email: string, slot: 1 | 2) =>
    request<{ message: string }>("/dashboard/backup-email", {
      method: "POST",
      body: JSON.stringify({ backup_email, slot }),
    }),

  verifyBackupEmail: (otp: string, pin: string, slot: 1 | 2) =>
    request<{ message: string }>("/dashboard/backup-email/verify", {
      method: "POST",
      body: JSON.stringify({ otp, pin, slot }),
    }),

  resolveBeneficiary: (payload: AddBeneficiaryPayload) =>
    request<ResolveBeneficiaryResponse>("/dashboard/beneficiaries/resolve", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  addBeneficiary: (payload: AddBeneficiaryPayload) =>
    request<{ message: string }>("/dashboard/beneficiaries", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  removeBeneficiary: (id: string, pin: string) =>
    request<{ message: string }>(`/dashboard/beneficiaries/${id}`, {
      method: "DELETE",
      body: JSON.stringify({ pin }),
    }),

  checkin: () => request<{ message: string; next_due_date: string }>("/dashboard/checkin", { method: "POST" }),

  updateCheckinConfig: (checkin_interval: string, grace_period: string, pin: string) =>
    request<{ message: string; next_due_date: string }>("/dashboard/checkin/config", {
      method: "PUT",
      body: JSON.stringify({ checkin_interval, grace_period, pin }),
    }),

  buyStock: (stock_symbol: string, units: number, pin: string) =>
    request<{ message: string }>("/trading/buy", {
      method: "POST",
      body: JSON.stringify({ stock_symbol, units, pin }),
    }),

  sellStock: (stock_symbol: string, units: number, pin: string) =>
    request<{ message: string }>("/trading/sell", {
      method: "POST",
      body: JSON.stringify({ stock_symbol, units, pin }),
    }),

  initiateFunding: (amount_kobo: number) =>
    request<InitiateFundingResponse>("/fund/initiate", {
      method: "POST",
      body: JSON.stringify({ amount_kobo }),
    }),
};
