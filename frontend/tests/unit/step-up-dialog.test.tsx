/**
 * The step-up dialog (ADR-05, Phase 4): password re-entry, and the emailed
 * one-time-code alternative — request, entry, resend, wrong code, and the
 * toggle back to the password field.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StepUpDialog } from "@/components/roles/step-up-dialog";
import { ApiError } from "@/lib/api";

const stepUpWithPassword = vi.hoisted(() => vi.fn());
const stepUpWithCode = vi.hoisted(() => vi.fn());
const requestStepUpCode = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return { ...actual, stepUpWithPassword, stepUpWithCode, requestStepUpCode };
});

function renderDialog(
  overrides: Partial<{ onConfirmed: () => void; onCancel: () => void }> = {},
) {
  const onConfirmed = overrides.onConfirmed ?? vi.fn();
  const onCancel = overrides.onCancel ?? vi.fn();
  const utils = render(
    <StepUpDialog open onConfirmed={onConfirmed} onCancel={onCancel} />,
  );
  return { ...utils, onConfirmed, onCancel };
}

beforeEach(() => {
  stepUpWithPassword.mockReset();
  stepUpWithCode.mockReset();
  requestStepUpCode.mockReset();
});

describe("StepUpDialog", () => {
  it("opens on the password field, disabled until something is typed", () => {
    renderDialog();
    expect(screen.getByText("Confirm it is you")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Confirm" })).toBeDisabled();
  });

  it("confirms with a password and reports back", async () => {
    stepUpWithPassword.mockResolvedValue(undefined);
    const { onConfirmed } = renderDialog();

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(stepUpWithPassword).toHaveBeenCalledWith("secret"),
    );
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledOnce());
  });

  it("shows an error and stays on the password field when it is wrong", async () => {
    stepUpWithPassword.mockRejectedValue(
      new ApiError(
        403,
        "step_up_required",
        "That password is not right.",
        "req-1",
      ),
    );
    const { onConfirmed } = renderDialog();

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(
      await screen.findByText("That password is not right."),
    ).toBeInTheDocument();
    expect(onConfirmed).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("requests a code and switches to code entry", async () => {
    requestStepUpCode.mockResolvedValue({
      detail: "A one-time code has been sent to your email.",
    });
    renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "Send me a code instead" }),
    );

    await waitFor(() => expect(requestStepUpCode).toHaveBeenCalledOnce());
    expect(
      await screen.findByText("A one-time code has been sent to your email."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("One-time code")).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("shows a friendly wait message when the code request is rate limited", async () => {
    requestStepUpCode.mockRejectedValue(
      new ApiError(429, "rate_limited", "Too many requests.", "req-2", {
        retry_after_seconds: 42 as unknown as string,
      }),
    );
    renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "Send me a code instead" }),
    );

    expect(
      await screen.findByText(
        "Too many attempts. Wait 42 seconds and try again.",
      ),
    ).toBeInTheDocument();
    // Refused — the form stays on the password field, nothing to enter a code into yet.
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("confirms with an emailed code and reports back", async () => {
    requestStepUpCode.mockResolvedValue({ detail: "Code sent." });
    stepUpWithCode.mockResolvedValue(undefined);
    const { onConfirmed } = renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "Send me a code instead" }),
    );
    await screen.findByLabelText("One-time code");

    fireEvent.change(screen.getByLabelText("One-time code"), {
      target: { value: "123456" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(stepUpWithCode).toHaveBeenCalledWith("123456"));
    await waitFor(() => expect(onConfirmed).toHaveBeenCalledOnce());
  });

  it("strips non-digits and caps the code at 6 characters", async () => {
    requestStepUpCode.mockResolvedValue({ detail: "Code sent." });
    renderDialog();
    fireEvent.click(
      screen.getByRole("button", { name: "Send me a code instead" }),
    );
    const input = await screen.findByLabelText("One-time code");

    fireEvent.change(input, { target: { value: "12a3-45678" } });
    expect(input).toHaveValue("123456");
  });

  it("reports a wrong or expired code and lets the caller resend", async () => {
    requestStepUpCode.mockResolvedValueOnce({ detail: "Code sent." });
    stepUpWithCode.mockRejectedValue(
      new ApiError(
        403,
        "step_up_required",
        "That code is not right or has expired.",
        "req-3",
      ),
    );
    const { onConfirmed } = renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "Send me a code instead" }),
    );
    fireEvent.change(await screen.findByLabelText("One-time code"), {
      target: { value: "000000" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    expect(
      await screen.findByText("That code is not right or has expired."),
    ).toBeInTheDocument();
    expect(onConfirmed).not.toHaveBeenCalled();
    expect(
      screen.getByRole("button", { name: "Resend code" }),
    ).toBeInTheDocument();
  });

  it("switches back to the password field on request", async () => {
    requestStepUpCode.mockResolvedValue({ detail: "Code sent." });
    renderDialog();

    fireEvent.click(
      screen.getByRole("button", { name: "Send me a code instead" }),
    );
    await screen.findByLabelText("One-time code");

    fireEvent.click(
      screen.getByRole("button", { name: "Use your password instead" }),
    );

    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.queryByLabelText("One-time code")).not.toBeInTheDocument();
  });

  it("calls onCancel from the Cancel button", () => {
    const { onCancel } = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
