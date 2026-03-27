"use client";

import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";

export default function VerifyEmailPage() {
  return (
    <main className="auth-screen">
      <AuthForm
        title="Verify Email"
        subtitle="Enter the 5-digit code sent to your inbox"
        fields={[
          { name: "email", label: "Email", type: "email" },
          { name: "code", label: "Verification Code" },
        ]}
        submitText="Verify"
        onSubmit={async (payload) => {
          const result = await api.verifyEmail({ email: payload.email, code: payload.code });
          if (result.error) {
            return { error: result.error };
          }
          return { success: result.data?.message ?? "Email verified" };
        }}
        footer={{ text: "Need to login now?", href: "/auth/login", linkLabel: "Go to login" }}
      />
    </main>
  );
}
