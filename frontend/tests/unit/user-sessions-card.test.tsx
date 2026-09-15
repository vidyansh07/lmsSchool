/**
 * The sessions section of the admin user page (ERP Phase 6, ADR-06):
 * loading/empty/error/success, `is_current` never rendered on this listing,
 * and ending a session behind a fresh step-up — a `403 step_up_required`
 * opens the step-up dialog and a successful step-up retries the same
 * revoke once.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UserSessionsCard } from "@/components/admin/user-sessions-card";
import { ApiError } from "@/lib/api";
import type { SessionRow } from "@/types/api";

const listUserSessions = vi.hoisted(() => vi.fn());
const revokeUserSession = vi.hoisted(() => vi.fn());
vi.mock("@/lib/sessions", () => ({ listUserSessions, revokeUserSession }));

// StepUpDialog (rendered for real) calls through to `lib/roles` — only the
// password path is exercised here, matching `mfa-settings-card.test.tsx`.
const stepUpWithPassword = vi.hoisted(() => vi.fn());
vi.mock("@/lib/roles", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/roles")>("@/lib/roles");
  return { ...actual, stepUpWithPassword };
});

function row(overrides: Partial<SessionRow>): SessionRow {
  return {
    id: "s1",
    device_label: "Chrome on macOS",
    ip: "203.0.113.4",
    created_at: "2026-09-10T10:00:00Z",
    last_seen_at: "2026-09-16T09:00:00Z",
    is_current: false,
    ...overrides,
  };
}

beforeEach(() => {
  listUserSessions.mockReset();
  revokeUserSession.mockReset();
  stepUpWithPassword.mockReset();
});

describe("UserSessionsCard — loading, empty, error", () => {
  it("shows a loading state while the account's sessions are fetched", async () => {
    let resolve!: (rows: SessionRow[]) => void;
    listUserSessions.mockReturnValue(
      new Promise<SessionRow[]>((r) => {
        resolve = r;
      }),
    );
    render(<UserSessionsCard userId="u1" />);
    expect(screen.getByText("Loading sessions…")).toBeInTheDocument();
    resolve([]);
    await screen.findByText("No active sessions");
  });

  it("shows an empty state when the account has no active sessions", async () => {
    listUserSessions.mockResolvedValue([]);
    render(<UserSessionsCard userId="u1" />);
    expect(await screen.findByText("No active sessions")).toBeInTheDocument();
    expect(listUserSessions).toHaveBeenCalledWith("u1");
  });

  it("shows an error and lets the caller retry, e.g. after a cross-centre 404", async () => {
    listUserSessions.mockRejectedValueOnce(
      new ApiError(404, "not_found", "Not found.", "req-1"),
    );
    listUserSessions.mockResolvedValueOnce([row({})]);
    render(<UserSessionsCard userId="u1" />);

    expect(await screen.findByText("Not found.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Chrome on macOS")).toBeInTheDocument();
  });
});

describe("UserSessionsCard — listing never shows is_current", () => {
  it("never renders a 'This device' badge, even when a row's is_current is true", async () => {
    listUserSessions.mockResolvedValue([row({ is_current: true })]);
    render(<UserSessionsCard userId="u1" />);

    await screen.findByText("Chrome on macOS");
    expect(screen.queryByText("This device")).not.toBeInTheDocument();
    // Every row on this listing gets a revoke control, is_current or not.
    expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument();
  });
});

describe("UserSessionsCard — revoking behind step-up", () => {
  it("ends a session immediately when step-up is already fresh", async () => {
    listUserSessions.mockResolvedValueOnce([row({})]);
    listUserSessions.mockResolvedValueOnce([]);
    revokeUserSession.mockResolvedValue(undefined);
    render(<UserSessionsCard userId="u1" />);

    await screen.findByText("Chrome on macOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() =>
      expect(revokeUserSession).toHaveBeenCalledWith("u1", "s1"),
    );
    expect(
      await screen.findByText('Signed "Chrome on macOS" out.'),
    ).toBeInTheDocument();
    expect(screen.getByText("No active sessions")).toBeInTheDocument();
  });

  it("opens the step-up dialog on a 403, then retries and succeeds", async () => {
    listUserSessions.mockResolvedValueOnce([row({})]);
    listUserSessions.mockResolvedValueOnce([]);
    revokeUserSession.mockRejectedValueOnce(
      new ApiError(403, "step_up_required", "Confirm it is you.", "req-2"),
    );
    revokeUserSession.mockResolvedValueOnce(undefined);
    stepUpWithPassword.mockResolvedValue(undefined);
    render(<UserSessionsCard userId="u1" />);

    await screen.findByText("Chrome on macOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    expect(await screen.findByText("Confirm it is you")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() =>
      expect(stepUpWithPassword).toHaveBeenCalledWith("secret"),
    );
    await waitFor(() => expect(revokeUserSession).toHaveBeenCalledTimes(2));
    expect(
      await screen.findByText('Signed "Chrome on macOS" out.'),
    ).toBeInTheDocument();
  });

  it("cancelling the step-up leaves the session untouched", async () => {
    listUserSessions.mockResolvedValue([row({})]);
    revokeUserSession.mockRejectedValue(
      new ApiError(403, "step_up_required", "Confirm it is you.", "req-3"),
    );
    render(<UserSessionsCard userId="u1" />);

    await screen.findByText("Chrome on macOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    expect(await screen.findByText("Confirm it is you")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByText("Confirm it is you")).not.toBeInTheDocument(),
    );
    expect(revokeUserSession).toHaveBeenCalledOnce();
    // The session is still listed — nothing succeeded.
    expect(screen.getByText("Chrome on macOS")).toBeInTheDocument();
  });

  it("shows a plain error for a non-step-up failure, without opening the step-up dialog", async () => {
    listUserSessions.mockResolvedValue([row({})]);
    revokeUserSession.mockRejectedValue(
      new ApiError(404, "not_found", "No such active session for that user.", "req-4"),
    );
    render(<UserSessionsCard userId="u1" />);

    await screen.findByText("Chrome on macOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    expect(
      await screen.findByText("No such active session for that user."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Confirm it is you")).not.toBeInTheDocument();
  });
});
