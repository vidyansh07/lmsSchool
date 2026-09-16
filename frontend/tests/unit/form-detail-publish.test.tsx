/**
 * Form detail: version history, opening a draft, and the publish
 * confirmation flow (dialog first, mutation only after confirming; a 409
 * "nothing changed" surfaces as a failure without closing silently).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FormDetail } from "@/components/forms/form-detail";
import { ApiError } from "@/lib/api";
import type {
  FormDefinitionDetail,
  FormVersionDetail,
} from "@/types/api";

const getFormDefinition = vi.hoisted(() => vi.fn());
const getFormVersion = vi.hoisted(() => vi.fn());
const publishFormVersion = vi.hoisted(() => vi.fn());
const unpublishFormVersion = vi.hoisted(() => vi.fn());
const createFormVersion = vi.hoisted(() => vi.fn());
const replaceFormFields = vi.hoisted(() => vi.fn());
vi.mock("@/lib/forms", async () => {
  const actual = await vi.importActual<typeof import("@/lib/forms")>("@/lib/forms");
  return {
    ...actual,
    getFormDefinition,
    getFormVersion,
    publishFormVersion,
    unpublishFormVersion,
    createFormVersion,
    replaceFormFields,
  };
});

vi.mock("@/components/auth-provider", () => ({
  useAuth: () => ({
    user: { role: "admin", capabilities: ["form.view", "form.manage"] },
    can: () => true,
  }),
}));

function definition(overrides: Partial<FormDefinitionDetail> = {}): FormDefinitionDetail {
  return {
    slug: "mock-interview",
    name: "Mock interview",
    entity: "activity",
    status: "active",
    published_version: null,
    draft_version: { id: "d1", number: 2, schema_hash: "new-hash", field_count: 1 },
    versions: [
      {
        id: "d1",
        number: 2,
        status: "draft",
        schema_hash: "new-hash",
        field_count: 1,
        published_at: null,
        published_by: null,
      },
      {
        id: "v1",
        number: 1,
        status: "archived",
        schema_hash: "old-hash",
        field_count: 1,
        published_at: "2026-01-01T00:00:00Z",
        published_by: "admin@grras.test",
      },
    ],
    ...overrides,
  };
}

function draftVersion(): FormVersionDetail {
  return {
    id: "d1",
    number: 2,
    status: "draft",
    fields: [
      {
        id: "f1",
        key: "score",
        label: "Score",
        help: "",
        type: "decimal",
        required: true,
        order: 0,
        group: "",
        options: null,
        validation: { min: 0, max: 10 },
        visible_to_student: true,
        performance_key: "score",
      },
    ],
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  getFormDefinition.mockResolvedValue(definition());
  getFormVersion.mockResolvedValue(draftVersion());
});

describe("FormDetail publish flow", () => {
  it("asks for confirmation before publishing and does not call the API until confirmed", async () => {
    render(<FormDetail slug="mock-interview" />);

    await waitFor(() => expect(screen.getByText("Mock interview")).toBeInTheDocument());
    await screen.findByRole("button", { name: "Publish" });

    fireEvent.click(screen.getByRole("button", { name: "Publish" }));

    expect(
      await screen.findByText("Publish version 2?"),
    ).toBeInTheDocument();
    expect(publishFormVersion).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText("Publish version 2?")).not.toBeInTheDocument();
    expect(publishFormVersion).not.toHaveBeenCalled();
  });

  it("publishes the version once the dialog is confirmed", async () => {
    publishFormVersion.mockResolvedValue(definition());
    render(<FormDetail slug="mock-interview" />);

    await screen.findByRole("button", { name: "Publish" });
    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    await screen.findByText("Publish version 2?");

    const dialogButtons = screen.getAllByRole("button", { name: "Publish" });
    const confirmButton = dialogButtons.at(-1);
    if (!confirmButton) throw new Error("Confirm button not found");
    fireEvent.click(confirmButton);

    await waitFor(() =>
      expect(publishFormVersion).toHaveBeenCalledWith("mock-interview", 2),
    );
    expect(await screen.findByText(/version 2 published/i)).toBeInTheDocument();
  });

  it("surfaces a 409 'nothing changed' failure without pretending success", async () => {
    publishFormVersion.mockRejectedValue(
      new ApiError(
        409,
        "conflict",
        "Nothing changed since the published version.",
        "req-9",
      ),
    );
    render(<FormDetail slug="mock-interview" />);

    await screen.findByRole("button", { name: "Publish" });
    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    await screen.findByText("Publish version 2?");

    const dialogButtons = screen.getAllByRole("button", { name: "Publish" });
    const confirmButton = dialogButtons.at(-1);
    if (!confirmButton) throw new Error("Confirm button not found");
    fireEvent.click(confirmButton);

    expect(
      await screen.findByText("Nothing changed since the published version."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Publish version 2?")).not.toBeInTheDocument();
  });
});
