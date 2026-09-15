/**
 * `LoginPage` (ERP Phase 5, ADR-05): the credentials form hands off to the
 * MFA-verify step on `{mfa_required: true}` instead of navigating away, and
 * finishing that step signs in exactly like an ordinary login would.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "@/app/login/page";
import { ApiError } from "@/lib/api";
import type { CurrentUser, MfaRequired } from "@/types/api";

const login = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth", () => ({ login }));

const verifyMfa = vi.hoisted(() => vi.fn());
const sendMfaEmailCode = vi.hoisted(() => vi.fn());
vi.mock("@/lib/mfa", () => ({ verifyMfa, sendMfaEmailCode }));

const setUser = vi.hoisted(() => vi.fn());
const authUser = vi.hoisted(() => ({ value: null as CurrentUser | null }));
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ user: authUser.value, setUser }),
}));

const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

const USER = { id: "u1", email: "a@b.test", mfa_enabled: true } as CurrentUser;
const MFA_REQUIRED: MfaRequired = {
  mfa_required: true,
  methods: ["totp", "email"],
  expires_in: 300,
};

beforeEach(() => {
  authUser.value = null;
  login.mockReset();
  verifyMfa.mockReset();
  sendMfaEmailCode.mockReset();
  setUser.mockReset();
  replace.mockReset();
});

function fillCredentials() {
  fireEvent.change(screen.getByLabelText("Email", { exact: false }), {
    target: { value: "a@b.test" },
  });
  fireEvent.change(screen.getByLabelText("Password", { exact: false }), {
    target: { value: "correct-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginPage", () => {
  it("signs straight in when the account has no MFA requirement", async () => {
    login.mockResolvedValue(USER);
    render(<LoginPage />);

    fillCredentials();

    await waitFor(() => expect(setUser).toHaveBeenCalledWith(USER));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("Verify it's you")).not.toBeInTheDocument();
  });

  it("switches to the MFA-verify step instead of navigating away", async () => {
    login.mockResolvedValue(MFA_REQUIRED);
    render(<LoginPage />);

    fillCredentials();

    expect(await screen.findByText("Verify it's you")).toBeInTheDocument();
    expect(setUser).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
    // Only the methods the server actually offered.
    expect(
      screen.getByRole("tab", { name: "Authenticator app" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Email code" })).toBeInTheDocument();
    expect(
      screen.queryByRole("tab", { name: "Recovery code" }),
    ).not.toBeInTheDocument();
  });

  it("finishes sign-in the same way an ordinary login does once MFA is verified", async () => {
    login.mockResolvedValue(MFA_REQUIRED);
    verifyMfa.mockResolvedValue(USER);
    render(<LoginPage />);

    fillCredentials();
    await screen.findByText("Verify it's you");
    fireEvent.change(
      screen.getByLabelText("Code from your authenticator app"),
      {
        target: { value: "123456" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() =>
      expect(verifyMfa).toHaveBeenCalledWith("totp", "123456"),
    );
    await waitFor(() => expect(setUser).toHaveBeenCalledWith(USER));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("returns to the credentials form from the MFA step without signing in", async () => {
    login.mockResolvedValue(MFA_REQUIRED);
    render(<LoginPage />);

    fillCredentials();
    await screen.findByText("Verify it's you");
    fireEvent.click(screen.getByRole("button", { name: "Back to sign in" }));

    expect(
      screen.getByLabelText("Email", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Verify it's you")).not.toBeInTheDocument();
    expect(setUser).not.toHaveBeenCalled();
  });

  it("shows the generic sign-in failure without ever mentioning MFA", async () => {
    login.mockRejectedValue(
      new ApiError(
        401,
        "authentication_failed",
        "Invalid credentials.",
        "req-1",
      ),
    );
    render(<LoginPage />);

    fillCredentials();

    expect(await screen.findByText("Invalid credentials.")).toBeInTheDocument();
    expect(screen.queryByText("Verify it's you")).not.toBeInTheDocument();
  });
});
