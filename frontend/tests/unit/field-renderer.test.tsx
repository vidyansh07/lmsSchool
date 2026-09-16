/**
 * FieldRenderer: representative field types (text, select, file, relation),
 * plus the read-only path and the visible-to-student filter.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FieldRenderer } from "@/components/forms/field-renderer";
import type { FormField } from "@/types/api";

function field(overrides: Partial<FormField>): FormField {
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

describe("FieldRenderer", () => {
  it("renders a text field and reports changes by key", () => {
    const onChange = vi.fn();
    render(
      <FieldRenderer
        fields={[field({ key: "topic", label: "Topic", type: "text" })]}
        values={{}}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("Topic"), {
      target: { value: "Closures" },
    });
    expect(onChange).toHaveBeenCalledWith("topic", "Closures");
  });

  it("renders a select field with its options", () => {
    const onChange = vi.fn();
    render(
      <FieldRenderer
        fields={[
          field({
            key: "outcome",
            label: "Outcome",
            type: "select",
            options: [
              { value: "ready", label: "Ready" },
              { value: "not_ready", label: "Not ready" },
            ],
          }),
        ]}
        values={{}}
        onChange={onChange}
      />,
    );
    fireEvent.change(screen.getByLabelText("Outcome"), {
      target: { value: "ready" },
    });
    expect(onChange).toHaveBeenCalledWith("outcome", "ready");
    expect(screen.getByRole("option", { name: "Not ready" })).toBeInTheDocument();
  });

  it("renders a file field as a file input honouring accept", () => {
    render(
      <FieldRenderer
        fields={[
          field({
            key: "resume",
            label: "Resume",
            type: "file",
            validation: { accept: [".pdf", ".docx"], max_mb: 5 },
          }),
        ]}
        values={{}}
      />,
    );
    const input = screen.getByLabelText("Resume") as HTMLInputElement;
    expect(input.type).toBe("file");
    expect(input.accept).toBe(".pdf,.docx");
  });

  it("renders a relation field as a text input naming the target model", () => {
    render(
      <FieldRenderer
        fields={[
          field({
            key: "lesson",
            label: "Lesson",
            type: "relation",
            options: { model: "batch" },
          }),
        ]}
        values={{}}
      />,
    );
    const input = screen.getByLabelText("Lesson") as HTMLInputElement;
    expect(input.placeholder).toBe("batch id");
  });

  it("shows a field-level error message", () => {
    render(
      <FieldRenderer
        fields={[field({ key: "topic", label: "Topic" })]}
        values={{}}
        onChange={vi.fn()}
        errors={{ topic: "This field is required." }}
      />,
    );
    expect(screen.getByText("This field is required.")).toBeInTheDocument();
  });

  it("filters to visible_to_student fields when studentOnly is set", () => {
    render(
      <FieldRenderer
        fields={[
          field({ key: "topic", label: "Topic", visible_to_student: true }),
          field({ key: "notes", label: "Private notes", visible_to_student: false }),
        ]}
        values={{}}
        studentOnly
      />,
    );
    expect(screen.getByLabelText("Topic")).toBeInTheDocument();
    expect(screen.queryByLabelText("Private notes")).not.toBeInTheDocument();
  });

  it("renders nothing to fill in when there are no fields", () => {
    render(<FieldRenderer fields={[]} values={{}} />);
    expect(screen.getByText(/no fields to show/i)).toBeInTheDocument();
  });
});
