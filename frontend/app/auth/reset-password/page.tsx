"use client";

import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";
import { useEffect } from "react";

export default function ResetPasswordPage() {
  useEffect(() => {
    void api.resetPasswordPage();
  }, []);

  return (
    <main className="auth-screen">
      <AuthForm
        title="Reset Password"
        subtitle="Use your email and reset code to set a new password"
        fields={[
          { name: "email", label: "Email", type: "email" },
          { name: "code", label: "Reset Code" },
          { name: "new_password", label: "New Password", type: "password" },
          { name: "confirm_password", label: "Confirm Password", type: "password" },
        ]}
        submitText="Reset Password"
        onSubmit={async (payload) => {
          const result = await api.resetPassword({
            email: payload.email,
            code: payload.code,
            new_password: payload.new_password,
            confirm_password: payload.confirm_password,
          });
          if (result.error) {
            return { error: result.error };
          }
          return { success: result.data?.message ?? "Password reset successful" };
        }}
        footer={{ text: "Need account access now?", href: "/auth/login", linkLabel: "Login" }}
      />
    </main>
  );
}
