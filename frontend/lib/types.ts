export type ApiError = {
  detail?: string;
  message?: string;
};

export type ApiResponse<T> = {
  data?: T;
  error?: string;
};

export type SignupPayload = {
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  password: string;
  confirm_password: string;
};

export type VerifyEmailPayload = {
  email: string;
  code: string;
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type ForgotPasswordPayload = {
  email: string;
};

export type ResetPasswordPayload = {
  email: string;
  code: string;
  new_password: string;
  confirm_password: string;
};

export type SetupPinPayload = {
  pin: string;
  confirm_pin: string;
  otp: string;
};

export type AddBeneficiaryPayload = {
  full_name: string;
  bank_name: string;
  account_number: string;
  percentage_share: number;
  pin: string;
  bank_code?: string;
  account_name?: string;
};

export type ResolveBeneficiaryResponse = {
  accountName: string;
  accountNumber: string;
  bankName: string;
  bankCode: string;
};

export type Profile = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  kyc_status: string;
  account_status: string;
  is_pin_set: boolean;
  is_first_login: boolean;
  backup_email: string | null;
  is_backup_email_verified: boolean;
  backup_email_2: string | null;
  is_backup_email_2_verified: boolean;
  created_at: string;
};

export type Balance = {
  balance: number;
  currency?: string;
};

export type Wallet = {
  balance: number;
  currency: string;
  transactions: Array<{
    id: string;
    type: string;
    amount: number;
    status: string;
    reference: string | null;
    narration: string | null;
    created_at: string;
  }>;
};

export type Portfolio = {
  portfolio: Array<{
    id: string;
    stock_symbol: string;
    stock_name: string;
    units: number;
    principal_amount: number;
    current_value: number;
  }>;
  summary: {
    total_invested: number;
    total_value: number;
    total_gain_loss: number;
    total_gain_loss_pct: number;
  };
};

export type Market = {
  stocks: Array<{
    symbol: string;
    name: string;
    current_price: number;
    sector: string;
    change: number | null;
    change_pct: number | null;
    owned_units: number;
  }>;
  count: number;
};

export type Holdings = {
  holdings: Array<{
    id: string;
    stock_symbol: string;
    stock_name: string;
    units: number;
    current_price: number;
    current_value: number;
    gain_loss: number;
    gain_loss_pct: number;
  }>;
  total_invested: number;
  total_current_value: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
};

export type TradeHistory = {
  trades: Array<{
    id: string;
    type: string;
    reference: string;
    amount: number;
    narration: string;
    created_at: string;
  }>;
  count: number;
};

export type CheckinStatus = {
  last_checkin_date: string;
  next_due_date: string;
  grace_deadline: string;
  checkin_interval_seconds: number;
  checkin_interval_days: number;
  grace_period_seconds: number;
  grace_period_days: number;
  status: string;
  seconds_remaining: number;
  days_remaining: number;
  disbursement_triggered: boolean;
};

export type Beneficiaries = {
  beneficiaries: Array<{
    id: string;
    full_name: string;
    bank_name: string;
    account_number: string;
    percentage_share: number;
    is_verified: boolean;
    created_at: string;
  }>;
  total_percentage: number;
};

export type InitiateFundingResponse = {
  txn_ref: string;
  amount_kobo: number;
  merchant_code: string;
  pay_item_id: string;
  customer_email: string;
  mode: string;
  site_redirect_url: string;
  inline_script_url: string;
};
