/**
 * The MFA-verify step of sign-in (ERP Phase 5, ADR-05): a tab per offered
 * method, the email "send code" hand-off, submitting a code, and the
 * failure/rate-limit paths.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MfaVerifyForm } from "@/components/auth/mfa-verify-form";
import { ApiError } from "@/lib/api";
import type { CurrentUser } from "@/types/api";

const sendMfaEmailCode = vi.hoisted(() => vi.fn());
const verifyMfa = vi.hoisted(() => vi.fn());
vi.mock("@/lib/mfa", () => ({ sendMfaEmailCode, verifyMfa }));

const USER = { id: "u1", email: "a@b.test" } as CurrentUser;

beforeEach(() => {
  sendMfaEmailCode.mockReset();
  verifyMfa.mockReset();
});

function renderForm(
  methods: Array<"totp" | "email" | "recovery">,
  overrides: Partial<{
    onVerified: (user: CurrentUser) => void;
    onBack: () => void;
  }> = {},
) {
  const onVerified = overrides.onVerified ?? vi.fn();
  const onBack = overrides.onBack ?? vi.fn();
  const utils = render(
    <MfaVerifyForm methods={methods} onVerified={onVerified} onBack={onBack} />,
  );
  return { ...utils, onVerified, onBack };
}

describe("MfaVerifyForm", () => {
  it("shows a tab only for each offered method, in the order given", () => {
    renderForm(["totp", "email", "recovery"]);
    expect(
      screen.getByRole("tab", { name: "Authenticator app" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Email code" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Recovery code" }),
    ).toBeInTheDocument();
  });

  it("renders no tabs at all for a single offered method", () => {
    renderForm(["email"]);
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Send code" }),
    ).toBeInTheDocument();
  });

  it("does not offer a method the server did not name", () => {
    renderForm(["email", "recovery"]);
    expect(
      screen.queryByRole("tab", { name: "Authenticator app" }),
    ).not.toBeInTheDocument();
  });

  it("submits a TOTP code and completes sign-in", async () => {
    verifyMfa.mockResolvedValue(USER);
    const { onVerified } = renderForm(["totp", "email"]);

    // "totp" is first, so it is the default tab — no send-code step for it.
    expect(
      screen.queryByRole("button", { name: "Send code" }),
    ).not.toBeInTheDocument();
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
    await waitFor(() => expect(onVerified).toHaveBeenCalledWith(USER));
  });

  it("requires sending an email code before the code field appears", async () => {
    sendMfaEmailCode.mockResolvedValue(undefined);
    renderForm(["email"]);

    expect(screen.queryByLabelText("One-time code")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));

    await waitFor(() => expect(sendMfaEmailCode).toHaveBeenCalledOnce());
    expect(
      await screen.findByText("A one-time code has been sent to your email."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("One-time code")).toBeInTheDocument();
  });

  it("submits the emailed code once sent", async () => {
    sendMfaEmailCode.mockResolvedValue(undefined);
    verifyMfa.mockResolvedValue(USER);
    const { onVerified } = renderForm(["email"]);

    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    await screen.findByLabelText("One-time code");
    fireEvent.change(screen.getByLabelText("One-time code"), {
      target: { value: "654321" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() =>
      expect(verifyMfa).toHaveBeenCalledWith("email", "654321"),
    );
    await waitFor(() => expect(onVerified).toHaveBeenCalledWith(USER));
  });

  it("strips non-hex characters and caps a recovery code at 11 characters", () => {
    renderForm(["recovery"]);
    const input = screen.getByLabelText("Recovery code");
    fireEvent.change(input, { target: { value: "ab12c!!-3d4e5-extra" } });
    expect(input).toHaveValue("AB12C-3D4E5");
  });

  it("reports a wrong code and never calls onVerified", async () => {
    verifyMfa.mockRejectedValue(
      new ApiError(
        400,
        "invalid_code",
        "That code is not right or has expired.",
        "req-1",
      ),
    );
    const { onVerified } = renderForm(["totp"]);

    fireEvent.change(
      screen.getByLabelText("Code from your authenticator app"),
      {
        target: { value: "000000" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    expect(
      await screen.findByText("That code is not right or has expired."),
    ).toBeInTheDocument();
    expect(onVerified).not.toHaveBeenCalled();
  });

  it("shows a friendly wait message when verification is rate limited", async () => {
    verifyMfa.mockRejectedValue(
      new ApiError(429, "rate_limited", "Too many attempts.", "req-2", {
        retry_after_seconds: 30 as unknown as string,
      }),
    );
    renderForm(["totp"]);

    fireEvent.change(
      screen.getByLabelText("Code from your authenticator app"),
      {
        target: { value: "111111" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));

    expect(
      await screen.findByText(
        "Too many attempts. Wait 30 seconds and try again.",
      ),
    ).toBeInTheDocument();
  });

  it("resets the code and any message when switching tabs", async () => {
    sendMfaEmailCode.mockResolvedValue(undefined);
    renderForm(["totp", "email"]);

    fireEvent.click(screen.getByRole("tab", { name: "Email code" }));
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    await screen.findByLabelText("One-time code");

    fireEvent.click(screen.getByRole("tab", { name: "Authenticator app" }));
    expect(
      screen.queryByText("A one-time code has been sent to your email."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByLabelText("Code from your authenticator app"),
    ).toHaveValue("");
  });

  it("calls onBack from the back link without touching the server", () => {
    const { onBack } = renderForm(["totp"]);
    fireEvent.click(screen.getByRole("button", { name: "Back to sign in" }));
    expect(onBack).toHaveBeenCalledOnce();
    expect(verifyMfa).not.toHaveBeenCalled();
  });

  it("disables Verify until a code of the right length is entered", () => {
    renderForm(["totp"]);
    const verifyButton = screen.getByRole("button", { name: "Verify" });
    expect(verifyButton).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText("Code from your authenticator app"),
      {
        target: { value: "12345" },
      },
    );
    expect(verifyButton).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText("Code from your authenticator app"),
      {
        target: { value: "123456" },
      },
    );
    expect(verifyButton).toBeEnabled();
  });
});
