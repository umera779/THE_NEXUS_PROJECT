"use client";

import Link from "next/link";
import { useState } from "react";
import { Banner, Button, Card, Input } from "./ui";

type Field = {
  name: string;
  label: string;
  type?: string;
  placeholder?: string;
};

type AuthFormProps = {
  title: string;
  subtitle: string;
  fields: Field[];
  submitText: string;
  onSubmit: (payload: Record<string, string>) => Promise<{ error?: string; success?: string }>;
  footer: { text: string; href: string; linkLabel: string };
};

export function AuthForm({ title, subtitle, fields, submitText, onSubmit, footer }: AuthFormProps) {
  const [form, setForm] = useState<Record<string, string>>(
    Object.fromEntries(fields.map((field) => [field.name, ""])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);

    const result = await onSubmit(form);

    if (result.error) {
      setError(result.error);
    }
    if (result.success) {
      setSuccess(result.success);
    }
    setBusy(false);
  }

  return (
    <Card className="auth-card" title={title} subtitle={subtitle}>
      <form onSubmit={handleSubmit} className="stack">
        {fields.map((field) => (
          <Input
            key={field.name}
            label={field.label}
            name={field.name}
            type={field.type ?? "text"}
            placeholder={field.placeholder}
            value={form[field.name] ?? ""}
            onChange={(event) =>
              setForm((previous) => ({
                ...previous,
                [field.name]: event.target.value,
              }))
            }
            required
          />
        ))}

        {error && <Banner tone="error">{error}</Banner>}
        {success && <Banner tone="success">{success}</Banner>}

        <Button type="submit" disabled={busy}>
          {busy ? "Please wait..." : submitText}
        </Button>
      </form>

      <p className="switch-auth">
        {footer.text} <Link href={footer.href}>{footer.linkLabel}</Link>
      </p>
    </Card>
  );
}
