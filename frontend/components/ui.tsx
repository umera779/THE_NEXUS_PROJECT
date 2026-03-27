"use client";

import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  title?: string;
  subtitle?: string;
};

export function Card({ title, subtitle, className = "", children, ...props }: CardProps) {
  return (
    <section className={`panel ${className}`.trim()} {...props}>
      {(title || subtitle) && (
        <header className="card-header">
          {title && <h3>{title}</h3>}
          {subtitle && <p>{subtitle}</p>}
        </header>
      )}
      {children}
    </section>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({ variant = "primary", className = "", children, ...props }: ButtonProps) {
  return (
    <button className={`btn btn-${variant} ${className}`.trim()} {...props}>
      {children}
    </button>
  );
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  right?: ReactNode;
};

export function Input({ label, hint, right, id, className = "", ...props }: InputProps) {
  const resolvedId = id ?? label.toLowerCase().replace(/\s+/g, "-");
  return (
    <label className="field" htmlFor={resolvedId}>
      <span className="field-label">{label}</span>
      <span className="field-wrap">
        <input id={resolvedId} className={`input ${className}`.trim()} {...props} />
        {right}
      </span>
      {hint && <small className="field-hint">{hint}</small>}
    </label>
  );
}

export function Banner({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" | "success" }) {
  return <div className={`banner banner-${tone}`}>{children}</div>;
}

export function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="stat">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
