"use client";

import { useRouter } from "next/navigation";
import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();

  return (
    <main className="auth-screen">
      <AuthForm
        title="Sign In"
        subtitle="Access your Legacy Portal account"
        fields={[
          { name: "email", label: "Email", type: "email", placeholder: "name@email.com" },
          { name: "password", label: "Password", type: "password" },
        ]}
        submitText="Login"
        onSubmit={async (payload) => {
          const result = await api.login({ email: payload.email, password: payload.password });
          if (result.error) {
            return { error: result.error };
          }
          router.push("/dashboard");
          return { success: result.data?.message ?? "Login successful" };
        }}
        footer={{ text: "No account yet?", href: "/auth/signup", linkLabel: "Create one" }}
      />
      <div className="auth-alt-links">
        <a href="/auth/forgot-password">Forgot password?</a>
        <a href="/auth/verify-email">Verify email</a>
      </div>
    </main>
  );
}
