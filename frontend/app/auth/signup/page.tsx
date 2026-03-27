"use client";

import { AuthForm } from "@/components/auth-form";
import { api } from "@/lib/api";

export default function SignupPage() {
  return (
    <main className="auth-screen">
      <AuthForm
        title="Create Account"
        subtitle="Open your investment legacy profile"
        fields={[
          { name: "first_name", label: "First Name" },
          { name: "last_name", label: "Last Name" },
          { name: "email", label: "Email", type: "email" },
          { name: "phone_number", label: "Phone Number" },
          { name: "password", label: "Password", type: "password" },
          { name: "confirm_password", label: "Confirm Password", type: "password" },
        ]}
        submitText="Register"
        onSubmit={async (payload) => {
          const result = await api.signup({
            first_name: payload.first_name,
            last_name: payload.last_name,
            email: payload.email,
            phone_number: payload.phone_number,
            password: payload.password,
            confirm_password: payload.confirm_password,
          });
          if (result.error) {
            return { error: result.error };
          }
          return { success: result.data?.message ?? "Registration successful" };
        }}
        footer={{ text: "Already have an account?", href: "/auth/login", linkLabel: "Sign in" }}
      />
    </main>
  );
}
