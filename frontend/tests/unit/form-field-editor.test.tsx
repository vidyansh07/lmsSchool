/**
 * FieldEditor: add/remove/reorder a field, and the preview panel surfacing
 * field-level errors from `POST /forms/{slug}/preview/`.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FieldEditor } from "@/components/forms/field-editor";
import { ApiError } from "@/lib/api";
import type { FormFieldInput } from "@/types/api";

const previewForm = vi.hoisted(() => vi.fn());
vi.mock("@/lib/forms", async () => {
  const actual = await vi.importActual<typeof import("@/lib/forms")>("@/lib/forms");
  return { ...actual, previewForm };
});

function textField(overrides: Partial<FormFieldInput>): FormFieldInput {
  return {
    id: overrides.key ?? "f1",
    key: "topic",
    label: "Topic",
    help: "",
    type: "text",
    required: false,
    order: 0,
    group: "",
    options: null,
    validation: {},
    visible_to_student: true,
    performance_key: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("FieldEditor", () => {
  it("adds a field", () => {
    const onChange = vi.fn();
    render(<FieldEditor slug="mock-interview" fields={[]} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ key: "", label: "", order: 0 }),
    ]);
  });

  it("removes a field", () => {
    const onChange = vi.fn();
    const fields = [
      textField({ id: "a", key: "topic", label: "Topic", order: 0 }),
      textField({ id: "b", key: "summary", label: "Summary", order: 1 }),
    ];
    render(<FieldEditor slug="mock-interview" fields={fields} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove field Topic" }));
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ key: "summary", order: 0 }),
    ]);
  });

  it("reorders a field down and renumbers order", () => {
    const onChange = vi.fn();
    const fields = [
      textField({ id: "a", key: "topic", label: "Topic", order: 0 }),
      textField({ id: "b", key: "summary", label: "Summary", order: 1 }),
    ];
    render(<FieldEditor slug="mock-interview" fields={fields} onChange={onChange} />);
    // Two rows both carry the "Move field down" label; the first (the
    // "Topic" row) is the one this test moves.
    const [moveDown] = screen.getAllByRole("button", { name: "Move field down" });
    fireEvent.click(moveDown!);
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ key: "summary", order: 0 }),
      expect.objectContaining({ key: "topic", order: 1 }),
    ]);
  });

  it("disables adding and editing when the version is published", () => {
    const fields = [textField({ id: "a", key: "topic", label: "Topic" })];
    render(
      <FieldEditor slug="mock-interview" fields={fields} onChange={vi.fn()} disabled />,
    );
    expect(screen.getByText(/this version is published/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add field/i })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Label", { exact: false })).toBeDisabled();
  });

  it("shows field-level errors from a failing preview", async () => {
    previewForm.mockRejectedValue(
      new ApiError(400, "validation_error", "The submitted data is invalid.", "req-1", {
        topic: ["This field is required."],
      }),
    );
    const fields = [textField({ id: "a", key: "topic", label: "Topic", required: true })];
    render(<FieldEditor slug="mock-interview" fields={fields} onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /check values/i }));

    await waitFor(() =>
      expect(screen.getByText("This field is required.")).toBeInTheDocument(),
    );
    expect(previewForm).toHaveBeenCalledWith("mock-interview", {});
  });

  it("shows a success notice when the preview passes", async () => {
    previewForm.mockResolvedValue({ errors: {} });
    const fields = [textField({ id: "a", key: "topic", label: "Topic" })];
    render(<FieldEditor slug="mock-interview" fields={fields} onChange={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /check values/i }));

    await waitFor(() =>
      expect(screen.getByText(/pass validation/i)).toBeInTheDocument(),
    );
  });
});
