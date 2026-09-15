/**
 * The sessions section of the security settings screen (ERP Phase 6,
 * ADR-06): loading/empty/error/success, revoking a non-current session with
 * confirmation, and that the current device has no revoke control at all —
 * it is not merely visually hidden, the button never renders.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionsCard } from "@/components/settings/sessions-card";
import { ApiError } from "@/lib/api";
import type { DetailResponse, SessionRow } from "@/types/api";

const listSessions = vi.hoisted(() => vi.fn());
const revokeSession = vi.hoisted(() => vi.fn());
const revokeOtherSessions = vi.hoisted(() => vi.fn());
vi.mock("@/lib/sessions", () => ({
  listSessions,
  revokeSession,
  revokeOtherSessions,
}));

const logoutEverywhere = vi.hoisted(() => vi.fn());
vi.mock("@/lib/auth", () => ({ logoutEverywhere }));

const replace = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

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
  listSessions.mockReset();
  revokeSession.mockReset();
  revokeOtherSessions.mockReset();
  logoutEverywhere.mockReset();
  replace.mockClear();
});

describe("SessionsCard — loading, empty, error", () => {
  it("shows a loading state while sessions are being fetched", async () => {
    let resolve!: (rows: SessionRow[]) => void;
    listSessions.mockReturnValue(
      new Promise<SessionRow[]>((r) => {
        resolve = r;
      }),
    );
    render(<SessionsCard />);
    expect(screen.getByText("Loading your sessions…")).toBeInTheDocument();
    resolve([]);
    await screen.findByText("No active sessions");
  });

  it("shows an empty state when there are no active sessions", async () => {
    listSessions.mockResolvedValue([]);
    render(<SessionsCard />);
    expect(await screen.findByText("No active sessions")).toBeInTheDocument();
  });

  it("shows an error and lets the caller retry", async () => {
    listSessions.mockRejectedValueOnce(
      new ApiError(500, "error", "Could not reach the server.", "req-1"),
    );
    listSessions.mockResolvedValueOnce([row({})]);
    render(<SessionsCard />);

    expect(
      await screen.findByText("Could not reach the server."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Chrome on macOS")).toBeInTheDocument();
    expect(listSessions).toHaveBeenCalledTimes(2);
  });
});

describe("SessionsCard — listing and revoking", () => {
  it("lists every session, badges the current one, and gives it no revoke control", async () => {
    listSessions.mockResolvedValue([
      row({ id: "current", device_label: "Firefox on Windows", is_current: true }),
      row({ id: "other", device_label: "Safari on iOS" }),
    ]);
    render(<SessionsCard />);

    await screen.findByText("Firefox on Windows");
    expect(screen.getByText("This device")).toBeInTheDocument();

    const rows = screen.getAllByTestId("session-row");
    const currentRow = rows.find((r) => r.textContent?.includes("Firefox on Windows"));
    const otherRow = rows.find((r) => r.textContent?.includes("Safari on iOS"));

    expect(currentRow).toBeDefined();
    expect(otherRow).toBeDefined();
    expect(
      currentRow!.querySelector("button"),
    ).not.toBeInTheDocument();
    expect(
      otherRow!.querySelector("button"),
    ).toBeInTheDocument();
  });

  it("revokes a session after confirmation and reloads the list", async () => {
    listSessions.mockResolvedValueOnce([
      row({ id: "other", device_label: "Safari on iOS" }),
    ]);
    listSessions.mockResolvedValueOnce([]);
    revokeSession.mockResolvedValue(undefined);
    render(<SessionsCard />);

    await screen.findByText("Safari on iOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    expect(await screen.findByText("Sign out this device?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(revokeSession).toHaveBeenCalledWith("other"));
    await waitFor(() =>
      expect(screen.getByText("No active sessions")).toBeInTheDocument(),
    );
  });

  it("cancelling the confirmation leaves the session untouched", async () => {
    listSessions.mockResolvedValue([
      row({ id: "other", device_label: "Safari on iOS" }),
    ]);
    render(<SessionsCard />);

    await screen.findByText("Safari on iOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await screen.findByText("Sign out this device?");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByText("Sign out this device?")).not.toBeInTheDocument(),
    );
    expect(revokeSession).not.toHaveBeenCalled();
  });

  it("shows an error inside the dialog when revoking fails", async () => {
    listSessions.mockResolvedValue([
      row({ id: "other", device_label: "Safari on iOS" }),
    ]);
    revokeSession.mockRejectedValue(
      new ApiError(404, "not_found", "No such active session of yours.", "r"),
    );
    render(<SessionsCard />);

    await screen.findByText("Safari on iOS");
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(
      await screen.findByText("No such active session of yours."),
    ).toBeInTheDocument();
  });

  it("signs out of every other session, leaving the current one", async () => {
    listSessions.mockResolvedValue([
      row({ id: "current", is_current: true }),
      row({ id: "other" }),
    ]);
    const detail: DetailResponse = { detail: "Signed out of 1 other session(s)." };
    revokeOtherSessions.mockResolvedValue(detail);
    render(<SessionsCard />);

    await screen.findByText("Sign out everywhere else");
    fireEvent.click(
      screen.getByRole("button", { name: "Sign out everywhere else" }),
    );

    expect(
      await screen.findByText("Signed out of 1 other session(s)."),
    ).toBeInTheDocument();
    expect(revokeOtherSessions).toHaveBeenCalledOnce();
  });

  it("does not offer 'sign out everywhere else' when there is nothing else", async () => {
    listSessions.mockResolvedValue([row({ id: "current", is_current: true })]);
    render(<SessionsCard />);

    await screen.findByText("This device");
    expect(
      screen.queryByRole("button", { name: "Sign out everywhere else" }),
    ).not.toBeInTheDocument();
  });

  it("signs out everywhere, including this device, and redirects to login", async () => {
    listSessions.mockResolvedValue([row({ id: "current", is_current: true })]);
    logoutEverywhere.mockResolvedValue({ detail: "Signed out of 1 session(s)." });
    render(<SessionsCard />);

    await screen.findByText("This device");
    fireEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));

    await waitFor(() => expect(logoutEverywhere).toHaveBeenCalledOnce());
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
