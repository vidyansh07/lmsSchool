/**
 * The form renderer's Meritto-style field types and conditional fields:
 * `show_if` follows the server's rule, a dependent dropdown offers only its
 * parent answer's choices, rating/consent/heading/hidden render as intended,
 * a file is uploaded and its id stored, and `valuesForSubmit` sends only
 * shown, answered fields in the shape the server validates.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  FieldRenderer,
  valuesForSubmit,
  visibleFieldKeys,
  type FormValues,
} from "@/components/forms/field-renderer";
import type { FormField } from "@/types/api";

const uploadFormFile = vi.hoisted(() => vi.fn());
vi.mock("@/lib/forms", async () => {
  const actual = await vi.importActual<typeof import("@/lib/forms")>("@/lib/forms");
  return { ...actual, uploadFormFile };
});

function field(overrides: Partial<FormField> & Pick<FormField, "key" | "type">): FormField {
  return {
    id: overrides.key,
    label: overrides.key,
    help: "",
    required: false,
    order: 0,
    group: "",
    options: null,
    validation: {},
    visible_to_student: false,
    performance_key: null,
    show_if: {},
    ...overrides,
  };
}

const STAGE = field({
  key: "stage",
  type: "select",
  order: 0,
  options: [
    { value: "interested", label: "Interested" },
    { value: "lost", label: "Lost" },
  ],
});
const REASON = field({
  key: "reason",
  type: "select",
  order: 1,
  required: true,
  options: [
    { value: "fees", label: "Fees" },
    { value: "competitor", label: "Competitor" },
  ],
  show_if: { field: "stage", op: "eq", value: "lost" },
});
const COMPETITOR = field({
  key: "competitor",
  type: "text",
  order: 2,
  show_if: { field: "reason", op: "eq", value: "competitor" },
});

function Harness({ fields, initial = {} }: { fields: FormField[]; initial?: FormValues }) {
  const [values, setValues] = useState<FormValues>(initial);
  return (
    <>
      <FieldRenderer
        fields={fields}
        values={values}
        onChange={(key, value) => setValues((current) => ({ ...current, [key]: value }))}
      />
      <output data-testid="values">{JSON.stringify(values)}</output>
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("visibleFieldKeys", () => {
  it("shows a field only while its parent is shown and matches", () => {
    const fields = [STAGE, REASON, COMPETITOR];
    expect(visibleFieldKeys(fields, {})).toEqual(new Set(["stage"]));
    expect(visibleFieldKeys(fields, { stage: "lost" })).toEqual(new Set(["stage", "reason"]));
    expect(
      visibleFieldKeys(fields, { stage: "lost", reason: "competitor" }),
    ).toEqual(new Set(["stage", "reason", "competitor"]));
    // A hidden parent hides its children even when their own rule matches.
    expect(
      visibleFieldKeys(fields, { stage: "interested", reason: "competitor" }),
    ).toEqual(new Set(["stage"]));
  });

  it("treats a boolean 'is not true' as shown while unanswered", () => {
    const same = field({ key: "same", type: "boolean" });
    const other = field({ key: "other", type: "phone", show_if: { field: "same", op: "ne", value: true } });
    expect(visibleFieldKeys([same, other], {}).has("other")).toBe(true);
    expect(visibleFieldKeys([same, other], { same: true }).has("other")).toBe(false);
  });
});

describe("valuesForSubmit", () => {
  it("drops hidden and empty answers, and sends numbers as numbers", () => {
    const year = field({ key: "year", type: "number" });
    const values = { stage: "interested", reason: "fees", year: "2024", competitor: "" };
    expect(valuesForSubmit([STAGE, REASON, COMPETITOR, year], values)).toEqual({
      stage: "interested",
      year: 2024,
    });
  });
});

describe("FieldRenderer", () => {
  it("reveals a conditional question when its answer calls for it", () => {
    render(<Harness fields={[STAGE, REASON]} />);
    expect(screen.queryByLabelText(/reason/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("stage"), { target: { value: "lost" } });
    expect(screen.getByLabelText(/reason/)).toBeInTheDocument();
  });

  it("offers a dependent dropdown's choices for the parent answer, and clears a stale one", () => {
    const state = field({
      key: "state",
      type: "select",
      order: 0,
      options: [
        { value: "rajasthan", label: "Rajasthan" },
        { value: "maharashtra", label: "Maharashtra" },
      ],
    });
    const city = field({
      key: "city",
      type: "dependent_select",
      order: 1,
      options: {
        parent: "state",
        choices: {
          rajasthan: [{ value: "jaipur", label: "Jaipur" }],
          maharashtra: [{ value: "pune", label: "Pune" }],
        },
      },
    });
    render(<Harness fields={[state, city]} />);
    const citySelect = screen.getByLabelText("city") as HTMLSelectElement;
    expect(citySelect).toBeDisabled();

    fireEvent.change(screen.getByLabelText("state"), { target: { value: "rajasthan" } });
    expect(Array.from(citySelect.options).map((option) => option.value)).toEqual(["", "jaipur"]);
    fireEvent.change(citySelect, { target: { value: "jaipur" } });

    fireEvent.change(screen.getByLabelText("state"), { target: { value: "maharashtra" } });
    expect(JSON.parse(screen.getByTestId("values").textContent ?? "{}")).toEqual({
      state: "maharashtra",
      city: "",
    });
  });

  it("renders a heading, hides a hidden value, and takes a rating and a consent", () => {
    render(
      <Harness
        fields={[
          field({ key: "intro", type: "heading", label: "About you", help: "A few details.", order: 0 }),
          field({ key: "utm_source", type: "hidden", order: 1 }),
          field({ key: "quality", type: "rating", label: "Lead quality", order: 2, validation: { max: 5 } }),
          field({ key: "agree", type: "consent", label: "I agree to be contacted", order: 3, required: true }),
        ]}
      />,
    );
    expect(screen.getByRole("heading", { name: "About you" })).toBeInTheDocument();
    expect(screen.getByText("A few details.")).toBeInTheDocument();
    expect(screen.queryByLabelText("utm_source")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "4 of 5" }));
    expect(screen.getByRole("button", { name: "4 of 5" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByLabelText(/I agree to be contacted/));
    expect(JSON.parse(screen.getByTestId("values").textContent ?? "{}")).toEqual({
      quality: 4,
      agree: true,
    });
  });

  it("uploads a chosen file and keeps its id as the answer", async () => {
    uploadFormFile.mockResolvedValue({
      id: "upload-1",
      filename: "cv.pdf",
      content_type: "application/pdf",
      size_bytes: 10,
      created_at: "2026-10-01T00:00:00Z",
    });
    render(<Harness fields={[field({ key: "resume", type: "file", label: "Resume" })]} />);
    const file = new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("Resume"), { target: { files: [file] } });

    await waitFor(() => expect(uploadFormFile).toHaveBeenCalledWith(file));
    expect(await screen.findByText("Uploaded: cv.pdf.")).toBeInTheDocument();
    expect(JSON.parse(screen.getByTestId("values").textContent ?? "{}")).toEqual({
      resume: "upload-1",
    });
  });
});
