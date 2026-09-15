/**
 * The MFA section of the security settings screen (ERP Phase 5, ADR-05):
 * enrolment (loading, error, success), the recovery-codes reveal — and
 * specifically that the codes are genuinely gone once dismissed, not just
 * hidden — and disable/regenerate behind a fresh step-up.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MfaSettingsCard } from "@/components/settings/mfa-settings-card";
import { ApiError } from "@/lib/api";
import type { MfaEnrolResponse, RecoveryCodesResponse } from "@/types/api";

const enrolTotp = vi.hoisted(() => vi.fn());
const confirmTotpEnrolment = vi.hoisted(() => vi.fn());
const disableTotp = vi.hoisted(() => vi.fn());
const regenerateRecoveryCodes = vi.hoisted(() => vi.fn());
vi.mock("@/lib/mfa", () => ({
  enrolTotp,
  confirmTotpEnrolment,
  disableTotp,
  regenerateRecoveryCodes,
}));

// StepUpDialog (rendered for real) calls through to `lib/roles` — only the
// password path is exercised here, the rest keep their real implementation.
const stepUpWithPassword = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return { ...actual, stepUpWithPassword };
});

const auth = vi.hoisted(() => ({ mfaEnabled: false }));
const refresh = vi.hoisted(() =>
  vi.fn(async () => {
    auth.mfaEnabled = true;
  }),
);
vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({ user: { mfa_enabled: auth.mfaEnabled }, refresh }),
}));

const ENROLMENT: MfaEnrolResponse = {
  secret_uri:
    "otpauth://totp/Grras%20LMS:a%40b.test?secret=ABCDEFGHIJKLMNOP&issuer=Grras+LMS",
  secret: "ABCDEFGHIJKLMNOP",
  qr_svg: '<svg data-testid="mfa-qr" viewBox="0 0 1 1"></svg>',
};

const CODES: RecoveryCodesResponse = {
  recovery_codes: ["AAAAA-11111", "BBBBB-22222", "CCCCC-33333"],
};

beforeEach(() => {
  auth.mfaEnabled = false;
  enrolTotp.mockReset();
  confirmTotpEnrolment.mockReset();
  disableTotp.mockReset();
  regenerateRecoveryCodes.mockReset();
  stepUpWithPassword.mockReset();
  refresh.mockClear();
});

describe("MfaSettingsCard — not yet enrolled", () => {
  it("offers to set up an authenticator app, with no manage controls", () => {
    render(<MfaSettingsCard />);
    expect(
      screen.getByRole("button", { name: "Set up authenticator app" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {
        name: "Disable two-factor authentication",
      }),
    ).not.toBeInTheDocument();
  });

  it("shows a loading state while the secret is being prepared", async () => {
    let resolveEnrol!: (value: MfaEnrolResponse) => void;
    enrolTotp.mockReturnValue(
      new Promise<MfaEnrolResponse>((resolve) => {
        resolveEnrol = resolve;
      }),
    );
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Set up authenticator app" }),
    );
    expect(
      await screen.findByText("Preparing your authenticator…"),
    ).toBeInTheDocument();

    resolveEnrol(ENROLMENT);
    expect(await screen.findByTestId("mfa-qr")).toBeInTheDocument();
  });

  it("shows an error and lets the caller retry when enrolment fails to start", async () => {
    enrolTotp.mockRejectedValueOnce(
      new ApiError(500, "error", "Could not reach the server.", "req-1"),
    );
    enrolTotp.mockResolvedValueOnce(ENROLMENT);
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Set up authenticator app" }),
    );
    expect(
      await screen.findByText("Could not reach the server."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("mfa-qr")).toBeInTheDocument();
    expect(enrolTotp).toHaveBeenCalledTimes(2);
  });

  it("renders the QR code and the manual-entry secret, confirms, and reveals recovery codes exactly once", async () => {
    enrolTotp.mockResolvedValue(ENROLMENT);
    confirmTotpEnrolment.mockResolvedValue(CODES);
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Set up authenticator app" }),
    );
    await screen.findByTestId("mfa-qr");
    expect(screen.getByDisplayValue("ABCDEFGHIJKLMNOP")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Code from your app"), {
      target: { value: "424242" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));

    await waitFor(() =>
      expect(confirmTotpEnrolment).toHaveBeenCalledWith("424242"),
    );
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());

    // The enrolment dialog is gone and the recovery codes are up instead.
    await waitFor(() =>
      expect(
        screen.queryByText("Set up two-factor authentication"),
      ).not.toBeInTheDocument(),
    );
    expect(
      await screen.findByText("Save your recovery codes"),
    ).toBeInTheDocument();
    for (const code of CODES.recovery_codes) {
      expect(screen.getByText(code)).toBeInTheDocument();
    }

    // Dismissing is the only way out — and it is genuinely gone, not just
    // visually hidden: closing the dialog clears the codes from this
    // component's own state, so nothing on the page can show them again.
    fireEvent.click(
      screen.getByRole("button", { name: "I've saved these codes" }),
    );

    // The codes themselves are gone from the DOM immediately — the dialog's
    // own exit animation may still be fading its (now code-less) shell out.
    for (const code of CODES.recovery_codes) {
      expect(screen.queryByText(code)).not.toBeInTheDocument();
    }
    expect(document.body.textContent).not.toContain(CODES.recovery_codes[0]);
    await waitFor(() =>
      expect(
        screen.queryByText("Save your recovery codes"),
      ).not.toBeInTheDocument(),
    );

    // Even a later, unrelated re-render (e.g. an action failing) leaves the
    // codes unreachable — they were never kept anywhere to redisplay.
    disableTotp.mockRejectedValueOnce(
      new ApiError(400, "mfa_not_enabled", "Not enabled.", "r"),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Disable two-factor authentication" }),
    );
    await screen.findByText("Not enabled.");
    for (const code of CODES.recovery_codes) {
      expect(screen.queryByText(code)).not.toBeInTheDocument();
    }
  });

  it("reports a wrong confirmation code and lets the caller retry without restarting enrolment", async () => {
    enrolTotp.mockResolvedValue(ENROLMENT);
    confirmTotpEnrolment.mockRejectedValueOnce(
      new ApiError(
        400,
        "invalid_code",
        "That code is not right or has expired.",
        "req-2",
      ),
    );
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Set up authenticator app" }),
    );
    await screen.findByTestId("mfa-qr");
    fireEvent.change(screen.getByLabelText("Code from your app"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Turn on" }));

    expect(
      await screen.findByText("That code is not right or has expired."),
    ).toBeInTheDocument();
    // Still on the same enrolment — the QR/secret are still there to retry.
    expect(screen.getByTestId("mfa-qr")).toBeInTheDocument();
    expect(enrolTotp).toHaveBeenCalledOnce();
  });

  it("closes the enrolment dialog on Cancel without confirming anything", async () => {
    enrolTotp.mockResolvedValue(ENROLMENT);
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Set up authenticator app" }),
    );
    await screen.findByTestId("mfa-qr");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(
        screen.queryByText("Set up two-factor authentication"),
      ).not.toBeInTheDocument(),
    );
    expect(confirmTotpEnrolment).not.toHaveBeenCalled();
  });
});

describe("MfaSettingsCard — already enrolled", () => {
  beforeEach(() => {
    auth.mfaEnabled = true;
  });

  it("offers to regenerate codes or disable, and hides the set-up button", () => {
    render(<MfaSettingsCard />);
    expect(
      screen.queryByRole("button", { name: "Set up authenticator app" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Regenerate recovery codes" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Disable two-factor authentication" }),
    ).toBeInTheDocument();
  });

  it("asks for a fresh step-up before disabling, then disables", async () => {
    disableTotp.mockRejectedValueOnce(
      new ApiError(
        403,
        "step_up_required",
        "Confirm it is you before doing this.",
        "req-3",
      ),
    );
    disableTotp.mockResolvedValueOnce(undefined);
    stepUpWithPassword.mockResolvedValue(undefined);
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Disable two-factor authentication" }),
    );
    expect(await screen.findByText("Confirm it is you")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(stepUpWithPassword).toHaveBeenCalledWith("secret"),
    );
    await waitFor(() => expect(disableTotp).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  });

  it("asks for a fresh step-up before regenerating, then reveals the new codes", async () => {
    regenerateRecoveryCodes.mockRejectedValueOnce(
      new ApiError(
        403,
        "step_up_required",
        "Confirm it is you before doing this.",
        "req-4",
      ),
    );
    regenerateRecoveryCodes.mockResolvedValueOnce(CODES);
    stepUpWithPassword.mockResolvedValue(undefined);
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Regenerate recovery codes" }),
    );
    expect(await screen.findByText("Confirm it is you")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(regenerateRecoveryCodes).toHaveBeenCalledTimes(2),
    );
    expect(
      await screen.findByText("Save your recovery codes"),
    ).toBeInTheDocument();
    expect(screen.getByText(CODES.recovery_codes[0]!)).toBeInTheDocument();
  });

  it("copies the recovery codes to the clipboard, never to any storage", async () => {
    regenerateRecoveryCodes.mockResolvedValue(CODES);
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Regenerate recovery codes" }),
    );
    await screen.findByText("Save your recovery codes");
    fireEvent.click(screen.getByRole("button", { name: "Copy all codes" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(CODES.recovery_codes.join("\n")),
    );
    expect(
      await screen.findByRole("button", { name: "Copied" }),
    ).toBeInTheDocument();
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("cancelling the step-up leaves MFA untouched", async () => {
    disableTotp.mockRejectedValue(
      new ApiError(
        403,
        "step_up_required",
        "Confirm it is you before doing this.",
        "req-5",
      ),
    );
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Disable two-factor authentication" }),
    );
    await screen.findByText("Confirm it is you");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByText("Confirm it is you")).not.toBeInTheDocument(),
    );
    expect(disableTotp).toHaveBeenCalledOnce();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("shows a plain error for a non-step-up failure, without opening the step-up dialog", async () => {
    disableTotp.mockRejectedValue(
      new ApiError(400, "mfa_not_enabled", "MFA is not enabled.", "req-6"),
    );
    render(<MfaSettingsCard />);

    fireEvent.click(
      screen.getByRole("button", { name: "Disable two-factor authentication" }),
    );

    expect(await screen.findByText("MFA is not enabled.")).toBeInTheDocument();
    expect(screen.queryByText("Confirm it is you")).not.toBeInTheDocument();
  });
});
