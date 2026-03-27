"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Beneficiaries, CheckinStatus, Holdings, Market, Portfolio, Profile, TradeHistory, Wallet } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";
import { Banner, Button, Card, Input, Stat } from "./ui";

type DataState = {
  profile: Profile | null;
  wallet: Wallet | null;
  portfolio: Portfolio | null;
  market: Market | null;
  holdings: Holdings | null;
  history: TradeHistory | null;
  checkin: CheckinStatus | null;
  beneficiaries: Beneficiaries | null;
};

const initialData: DataState = {
  profile: null,
  wallet: null,
  portfolio: null,
  market: null,
  holdings: null,
  history: null,
  checkin: null,
  beneficiaries: null,
};

export function DashboardShell() {
  const [data, setData] = useState<DataState>(initialData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [pinSetup, setPinSetup] = useState({ pin: "", confirm_pin: "", otp: "" });
  const [backupEmail, setBackupEmail] = useState({ backup: "", slot: "1", otp: "", pin: "" });
  const [trade, setTrade] = useState({ symbol: "", units: "", pin: "", mode: "buy" as "buy" | "sell" });
  const [beneficiary, setBeneficiary] = useState({
    full_name: "",
    bank_name: "",
    account_number: "",
    percentage_share: "",
    pin: "",
  });
  const [beneficiaryResolved, setBeneficiaryResolved] = useState<{ bankCode?: string; accountName?: string } | null>(null);
  const [checkinConfig, setCheckinConfig] = useState({ checkin_interval: "00:07:00:00", grace_period: "00:01:00:00", pin: "" });
  const [funding, setFunding] = useState({ amount_naira: "" });
  const [deleteBeneficiaryPin, setDeleteBeneficiaryPin] = useState<Record<string, string>>({});

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [profile, wallet, portfolio, market, holdings, history, checkin, beneficiaries] = await Promise.all([
      api.profile(),
      api.wallet(),
      api.portfolio(),
      api.market(),
      api.holdings(),
      api.history(),
      api.checkinStatus(),
      api.beneficiaries(),
    ]);

    const firstError = [
      profile.error,
      wallet.error,
      portfolio.error,
      market.error,
      holdings.error,
      history.error,
      checkin.error,
      beneficiaries.error,
    ].find((item) => typeof item === "string");

    if (firstError) {
      setError(firstError);
    }

    setData({
      profile: profile.data ?? null,
      wallet: wallet.data ?? null,
      portfolio: portfolio.data ?? null,
      market: market.data ?? null,
      holdings: holdings.data ?? null,
      history: history.data ?? null,
      checkin: checkin.data ?? null,
      beneficiaries: beneficiaries.data ?? null,
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const stats = useMemo(() => {
    const walletBalance = data.wallet?.balance ?? 0;
    const invested = data.portfolio?.summary.total_invested ?? 0;
    const totalValue = data.portfolio?.summary.total_value ?? 0;
    const gain = data.portfolio?.summary.total_gain_loss ?? 0;
    return {
      walletBalance,
      invested,
      totalValue,
      gain,
    };
  }, [data]);

  async function requestPinOtp() {
    const result = await api.requestPinOtp();
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
  }

  async function submitPinSetup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await api.setupPin(pinSetup);
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      setPinSetup({ pin: "", confirm_pin: "", otp: "" });
      await loadAll();
    }
  }

  async function saveBackupEmail(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await api.setBackupEmail(backupEmail.backup, Number(backupEmail.slot) as 1 | 2);
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
  }

  async function verifyBackupEmail(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await api.verifyBackupEmail(
      backupEmail.otp,
      backupEmail.pin,
      Number(backupEmail.slot) as 1 | 2,
    );
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      await loadAll();
    }
  }

  async function submitTrade(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const units = Number(trade.units);
    if (!Number.isFinite(units) || units <= 0) {
      setActionMessage("Units must be greater than 0");
      return;
    }
    const result =
      trade.mode === "buy"
        ? await api.buyStock(trade.symbol.toUpperCase(), units, trade.pin)
        : await api.sellStock(trade.symbol.toUpperCase(), units, trade.pin);
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      setTrade({ symbol: "", units: "", pin: "", mode: trade.mode });
      await loadAll();
    }
  }

  async function resolveBeneficiary(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const percentage = Number(beneficiary.percentage_share);
    if (!Number.isFinite(percentage) || percentage <= 0 || percentage > 100) {
      setActionMessage("Percentage share must be between 0.01 and 100");
      return;
    }
    const result = await api.resolveBeneficiary({
      ...beneficiary,
      percentage_share: percentage,
    });
    if (result.error) {
      setActionMessage(result.error);
      return;
    }
    if (result.data) {
      setBeneficiaryResolved({ bankCode: result.data.bankCode, accountName: result.data.accountName });
      setActionMessage(`Verified account: ${result.data.accountName}`);
    }
  }

  async function addBeneficiary(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const percentage = Number(beneficiary.percentage_share);
    if (!Number.isFinite(percentage) || percentage <= 0 || percentage > 100) {
      setActionMessage("Percentage share must be between 0.01 and 100");
      return;
    }
    const result = await api.addBeneficiary({
      ...beneficiary,
      percentage_share: percentage,
      bank_code: beneficiaryResolved?.bankCode,
      account_name: beneficiaryResolved?.accountName,
    });
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      setBeneficiary({ full_name: "", bank_name: "", account_number: "", percentage_share: "", pin: "" });
      setBeneficiaryResolved(null);
      await loadAll();
    }
  }

  async function removeBeneficiary(id: string) {
    const pin = deleteBeneficiaryPin[id];
    if (!pin) {
      setActionMessage("Enter PIN to remove beneficiary");
      return;
    }
    const result = await api.removeBeneficiary(id, pin);
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      setDeleteBeneficiaryPin((previous) => {
        const next = { ...previous };
        delete next[id];
        return next;
      });
      await loadAll();
    }
  }

  async function doCheckin() {
    const result = await api.checkin();
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      await loadAll();
    }
  }

  async function saveCheckinConfig(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await api.updateCheckinConfig(
      checkinConfig.checkin_interval,
      checkinConfig.grace_period,
      checkinConfig.pin,
    );
    setActionMessage(result.error ?? result.data?.message ?? "Completed");
    if (!result.error) {
      setCheckinConfig((previous) => ({ ...previous, pin: "" }));
      await loadAll();
    }
  }

  async function initiateFunding(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amountNaira = Number(funding.amount_naira);
    if (!Number.isFinite(amountNaira) || amountNaira < 100) {
      setActionMessage("Minimum funding amount is ₦100");
      return;
    }
    const amount_kobo = Math.round(amountNaira * 100);
    const result = await api.initiateFunding(amount_kobo);
    if (result.error || !result.data) {
      setActionMessage(result.error ?? "Could not initiate payment");
      return;
    }
    setActionMessage(`Funding initiated. Transaction reference: ${result.data.txn_ref}`);
    setFunding({ amount_naira: "" });
  }

  async function logout() {
    const result = await api.logout();
    setActionMessage(result.error ?? result.data?.message ?? "Logged out");
    window.location.href = "/auth/login";
  }

  if (loading) {
    return <div className="loading-screen">Loading your investment workspace...</div>;
  }

  return (
    <main className="dashboard-root">
      <header className="topbar">
        <div>
          <p className="eyebrow">Legacy Portal</p>
          <h1>
            Welcome, {data.profile?.first_name} {data.profile?.last_name}
          </h1>
          <p className="subtle">Secure estate-ready investment management from one dashboard.</p>
        </div>
        <div className="topbar-actions">
          <Button variant="secondary" onClick={() => void loadAll()}>
            Refresh
          </Button>
          <Button variant="ghost" onClick={() => void logout()}>
            Logout
          </Button>
        </div>
      </header>

      {error && <Banner tone="error">{error}</Banner>}
      {actionMessage && <Banner tone="info">{actionMessage}</Banner>}

      <section className="stats-grid">
        <Stat label="Wallet Balance" value={formatMoney(stats.walletBalance)} />
        <Stat label="Total Invested" value={formatMoney(stats.invested)} />
        <Stat label="Portfolio Value" value={formatMoney(stats.totalValue)} />
        <Stat label="Total Gain/Loss" value={formatMoney(stats.gain)} />
      </section>

      <section className="dashboard-grid">
        <Card title="Profile" subtitle="Identity and account posture">
          <div className="list-grid">
            <span>Email</span>
            <strong>{data.profile?.email ?? "-"}</strong>
            <span>Phone</span>
            <strong>{data.profile?.phone_number ?? "-"}</strong>
            <span>KYC</span>
            <strong>{data.profile?.kyc_status ?? "-"}</strong>
            <span>Account</span>
            <strong>{data.profile?.account_status ?? "-"}</strong>
            <span>First Login</span>
            <strong>{String(data.profile?.is_first_login ?? false)}</strong>
          </div>
        </Card>

        <Card title="PIN Setup" subtitle="Required for transactions and beneficiaries">
          <div className="inline-actions">
            <Button variant="secondary" onClick={() => void requestPinOtp()}>
              Request PIN OTP
            </Button>
          </div>
          <form className="stack" onSubmit={submitPinSetup}>
            <Input
              label="PIN"
              value={pinSetup.pin}
              onChange={(event) => setPinSetup((previous) => ({ ...previous, pin: event.target.value }))}
              minLength={6}
              maxLength={6}
              required
            />
            <Input
              label="Confirm PIN"
              value={pinSetup.confirm_pin}
              onChange={(event) => setPinSetup((previous) => ({ ...previous, confirm_pin: event.target.value }))}
              minLength={6}
              maxLength={6}
              required
            />
            <Input
              label="OTP"
              value={pinSetup.otp}
              onChange={(event) => setPinSetup((previous) => ({ ...previous, otp: event.target.value }))}
              minLength={6}
              maxLength={6}
              required
            />
            <Button type="submit">Set PIN</Button>
          </form>
        </Card>

        <Card title="Backup Email" subtitle="Disbursement continuity channels">
          <form className="stack" onSubmit={saveBackupEmail}>
            <Input
              label="Backup Email"
              type="email"
              value={backupEmail.backup}
              onChange={(event) => setBackupEmail((previous) => ({ ...previous, backup: event.target.value }))}
              required
            />
            <Input
              label="Slot"
              value={backupEmail.slot}
              onChange={(event) => setBackupEmail((previous) => ({ ...previous, slot: event.target.value }))}
              placeholder="1 or 2"
              required
            />
            <Button type="submit">Save Backup Email</Button>
          </form>
          <form className="stack" onSubmit={verifyBackupEmail}>
            <Input
              label="OTP"
              value={backupEmail.otp}
              onChange={(event) => setBackupEmail((previous) => ({ ...previous, otp: event.target.value }))}
              required
            />
            <Input
              label="PIN"
              value={backupEmail.pin}
              onChange={(event) => setBackupEmail((previous) => ({ ...previous, pin: event.target.value }))}
              required
            />
            <Button type="submit" variant="secondary">
              Verify Backup Email
            </Button>
          </form>
        </Card>

        <Card title="Funding" subtitle="Create Interswitch funding session">
          <form className="stack" onSubmit={initiateFunding}>
            <Input
              label="Amount (₦)"
              type="number"
              value={funding.amount_naira}
              onChange={(event) => setFunding({ amount_naira: event.target.value })}
              min={100}
              required
            />
            <Button type="submit">Initiate Funding</Button>
          </form>
        </Card>

        <Card title="Check-in" subtitle="Proof-of-life controls">
          <div className="list-grid">
            <span>Status</span>
            <strong>{data.checkin?.status ?? "-"}</strong>
            <span>Next Due</span>
            <strong>{data.checkin?.next_due_date ? formatDate(data.checkin.next_due_date) : "-"}</strong>
            <span>Grace Deadline</span>
            <strong>{data.checkin?.grace_deadline ? formatDate(data.checkin.grace_deadline) : "-"}</strong>
          </div>
          <div className="inline-actions">
            <Button onClick={() => void doCheckin()}>Check In Now</Button>
          </div>
          <form className="stack" onSubmit={saveCheckinConfig}>
            <Input
              label="Check-in Interval (DD:HH:MM:SS)"
              value={checkinConfig.checkin_interval}
              onChange={(event) =>
                setCheckinConfig((previous) => ({ ...previous, checkin_interval: event.target.value }))
              }
              required
            />
            <Input
              label="Grace Period (DD:HH:MM:SS)"
              value={checkinConfig.grace_period}
              onChange={(event) => setCheckinConfig((previous) => ({ ...previous, grace_period: event.target.value }))}
              required
            />
            <Input
              label="PIN"
              value={checkinConfig.pin}
              onChange={(event) => setCheckinConfig((previous) => ({ ...previous, pin: event.target.value }))}
              required
            />
            <Button type="submit" variant="secondary">
              Update Check-in Config
            </Button>
          </form>
        </Card>

        <Card title="Trade Stocks" subtitle="Buy/sell at live market prices">
          <form className="stack" onSubmit={submitTrade}>
            <Input
              label="Action"
              value={trade.mode}
              onChange={(event) =>
                setTrade((previous) => ({
                  ...previous,
                  mode: event.target.value === "sell" ? "sell" : "buy",
                }))
              }
              placeholder="buy or sell"
              required
            />
            <Input
              label="Stock Symbol"
              value={trade.symbol}
              onChange={(event) => setTrade((previous) => ({ ...previous, symbol: event.target.value }))}
              required
            />
            <Input
              label="Units"
              type="number"
              step="0.0001"
              value={trade.units}
              onChange={(event) => setTrade((previous) => ({ ...previous, units: event.target.value }))}
              required
            />
            <Input
              label="PIN"
              value={trade.pin}
              onChange={(event) => setTrade((previous) => ({ ...previous, pin: event.target.value }))}
              minLength={6}
              maxLength={6}
              required
            />
            <Button type="submit">Submit Trade</Button>
          </form>
        </Card>

        <Card title="Beneficiaries" subtitle="Resolve account first, then commit with PIN">
          <form className="stack" onSubmit={resolveBeneficiary}>
            <Input
              label="Full Name"
              value={beneficiary.full_name}
              onChange={(event) => setBeneficiary((previous) => ({ ...previous, full_name: event.target.value }))}
              required
            />
            <Input
              label="Bank Name"
              value={beneficiary.bank_name}
              onChange={(event) => setBeneficiary((previous) => ({ ...previous, bank_name: event.target.value }))}
              required
            />
            <Input
              label="Account Number"
              value={beneficiary.account_number}
              onChange={(event) => setBeneficiary((previous) => ({ ...previous, account_number: event.target.value }))}
              required
            />
            <Input
              label="Percentage Share"
              type="number"
              value={beneficiary.percentage_share}
              onChange={(event) =>
                setBeneficiary((previous) => ({ ...previous, percentage_share: event.target.value }))
              }
              required
            />
            <Button type="submit" variant="secondary">
              Resolve Account
            </Button>
          </form>

          <form className="stack" onSubmit={addBeneficiary}>
            <Input
              label="PIN"
              value={beneficiary.pin}
              onChange={(event) => setBeneficiary((previous) => ({ ...previous, pin: event.target.value }))}
              minLength={6}
              maxLength={6}
              required
            />
            <Button type="submit">Add Beneficiary</Button>
          </form>

          <div className="records">
            {(data.beneficiaries?.beneficiaries ?? []).map((item) => (
              <article key={item.id} className="record-row">
                <div>
                  <strong>{item.full_name}</strong>
                  <p>
                    {item.bank_name} • {item.account_number} • {item.percentage_share}%
                  </p>
                </div>
                <div className="record-actions">
                  <input
                    className="input small"
                    placeholder="PIN"
                    value={deleteBeneficiaryPin[item.id] ?? ""}
                    onChange={(event) =>
                      setDeleteBeneficiaryPin((previous) => ({ ...previous, [item.id]: event.target.value }))
                    }
                  />
                  <Button variant="ghost" onClick={() => void removeBeneficiary(item.id)}>
                    Remove
                  </Button>
                </div>
              </article>
            ))}
          </div>
        </Card>

        <Card title="Portfolio Snapshot" subtitle="Investments and market overview">
          <div className="records">
            {(data.holdings?.holdings ?? []).map((holding) => (
              <article key={holding.id} className="record-row">
                <div>
                  <strong>{holding.stock_symbol}</strong>
                  <p>
                    {holding.units} units • {formatMoney(holding.current_value)}
                  </p>
                </div>
                <div>
                  <strong>{formatMoney(holding.gain_loss)}</strong>
                  <p>{holding.gain_loss_pct}%</p>
                </div>
              </article>
            ))}
          </div>

          <div className="records">
            {(data.market?.stocks ?? []).slice(0, 8).map((stock) => (
              <article key={stock.symbol} className="record-row">
                <div>
                  <strong>{stock.symbol}</strong>
                  <p>{stock.name}</p>
                </div>
                <div>
                  <strong>{formatMoney(stock.current_price)}</strong>
                  <p>{stock.change_pct ?? 0}%</p>
                </div>
              </article>
            ))}
          </div>
        </Card>

        <Card title="Transaction Trail" subtitle="Wallet and trade transactions">
          <div className="records">
            {(data.wallet?.transactions ?? []).slice(0, 8).map((transaction) => (
              <article key={transaction.id} className="record-row">
                <div>
                  <strong>{transaction.type}</strong>
                  <p>{transaction.narration ?? "No narration"}</p>
                </div>
                <div>
                  <strong>{formatMoney(transaction.amount)}</strong>
                  <p>{formatDate(transaction.created_at)}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="records">
            {(data.history?.trades ?? []).slice(0, 8).map((tradeRecord) => (
              <article key={tradeRecord.id} className="record-row">
                <div>
                  <strong>{tradeRecord.type}</strong>
                  <p>{tradeRecord.narration}</p>
                </div>
                <div>
                  <strong>{formatMoney(tradeRecord.amount)}</strong>
                  <p>{formatDate(tradeRecord.created_at)}</p>
                </div>
              </article>
            ))}
          </div>
        </Card>
      </section>
    </main>
  );
}
