"use client";

import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  return (
    <main className="auth-screen">
      <AuthForm
        title="Forgot Password"
        subtitle="Request a reset code to your verified email"
        fields={[{ name: "email", label: "Email", type: "email" }]}
        submitText="Send Reset Code"
        onSubmit={async (payload) => {
          const result = await api.forgotPassword({ email: payload.email });
          if (result.error) {
            return { error: result.error };
          }
          return { success: result.data?.message ?? "Reset code sent" };
        }}
        footer={{ text: "Remembered your password?", href: "/auth/login", linkLabel: "Back to login" }}
      />
    </main>
  );
}
